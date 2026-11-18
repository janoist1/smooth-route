#!/usr/bin/env python3
"""
Cheap partial fine-tuning experiment: train only the LAST N transformer blocks
of DINOv2-small (+ final LayerNorm + a linear regression head on CLS ⊕
patch-mean, i.e. the same read-out as the production recipe) on the official
spatial CV folds, and compare against the frozen-feature champion.

Cheap because the frozen part runs once: hidden states after block (12 - N)
are cached for every image (fp16, ~375 MB for N=2), and each fold only trains
N blocks on those cached tokens — seconds per epoch on MPS. The trade-off: no
pixel-level augmentation (the cached tokens are fixed); random patch-token
dropout is used as a cheap regulariser instead.

Evaluation: identical to the gate — spatial 5-fold (1 km cells, seed 42),
cut-points tuned per outer fold on inner spatial OOF predictions (which means
5 x (1 + 4) fine-tunes).

Usage:
  .venv/bin/python ml/finetune_lastblocks.py [--blocks 2] [--epochs 8]
        [--images-dir data/images] [--no-nested]
"""
import argparse
import copy
import os
import sys
import time

import numpy as np
import pandas as pd
import torch
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spatial_cv as S  # noqa: E402

ROOT = S.ROOT
CACHE = os.path.join(ROOT, "ml", "cache")
MODEL = "facebook/dinov2-small"
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"


def load_dataset():
    df = pd.read_csv(os.path.join(CACHE, "dataset_v2.csv"))
    keep = (df["rqi"].values != 5) & (df["is_road_prob"].values >= 0.55)
    return df[keep].reset_index(drop=True)


@torch.no_grad()
def cache_tokens(df, images_dir, n_frozen, model):
    path = os.path.join(CACHE, f"ft_tokens_small_L{n_frozen}.npz")
    if os.path.exists(path):
        z = np.load(path, allow_pickle=True)
        if list(z["files"]) == list(df["image_filename"]):
            return z["h"]
    from transformers import AutoImageProcessor
    proc = AutoImageProcessor.from_pretrained(MODEL)
    out = []
    files = list(df["image_filename"])
    for i in range(0, len(files), 32):
        imgs = [Image.open(os.path.join(images_dir, f)).convert("RGB")
                for f in files[i:i + 32]]
        inp = proc(images=imgs, return_tensors="pt").to(DEVICE)
        hs = model(**inp, output_hidden_states=True).hidden_states[n_frozen]
        out.append(hs.half().cpu().numpy())
        print(f"   tokens {i + len(imgs)}/{len(files)}", end="\r")
    print()
    h = np.concatenate(out)
    np.savez(path, h=h, files=np.array(files, dtype=object))
    return h


class Tail(torch.nn.Module):
    def __init__(self, base, n_frozen):
        super().__init__()
        self.blocks = torch.nn.ModuleList(
            copy.deepcopy(base.encoder.layer[n_frozen:]))
        self.norm = copy.deepcopy(base.layernorm)
        d = base.config.hidden_size
        self.head = torch.nn.Linear(2 * d, 1)
        torch.nn.init.zeros_(self.head.weight)
        torch.nn.init.constant_(self.head.bias, 2.0)

    def forward(self, h, patch_drop=0.0):
        if self.training and patch_drop > 0:
            n = h.shape[1] - 1
            keep = int(round(n * (1 - patch_drop)))
            idx = torch.rand(h.shape[0], n, device=h.device).argsort(1)[:, :keep] + 1
            h = torch.cat([h[:, :1], torch.gather(
                h, 1, idx[..., None].expand(-1, -1, h.shape[2]))], 1)
        for blk in self.blocks:
            o = blk(h)
            h = o[0] if isinstance(o, tuple) else o
        h = self.norm(h)
        feat = torch.cat([h[:, 0], h[:, 1:].mean(1)], 1)
        return self.head(feat).squeeze(1)


def train_predict(base, n_frozen, H, y, tr, te, args, seed):
    torch.manual_seed(seed)
    net = Tail(base, n_frozen).to(DEVICE)
    opt = torch.optim.AdamW([
        {"params": net.blocks.parameters(), "lr": args.lr},
        {"params": net.norm.parameters(), "lr": args.lr},
        {"params": net.head.parameters(), "lr": args.head_lr},
    ], weight_decay=0.05)
    steps = args.epochs * int(np.ceil(len(tr) / args.batch))
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=[args.lr, args.lr, args.head_lr], total_steps=steps,
        pct_start=0.15)
    yt = torch.tensor(y, dtype=torch.float32)
    rng = np.random.default_rng(seed)
    net.train()
    for _ in range(args.epochs):
        perm = rng.permutation(tr)
        for i in range(0, len(perm), args.batch):
            b = perm[i:i + args.batch]
            hb = torch.from_numpy(H[b]).float().to(DEVICE)
            loss = torch.nn.functional.smooth_l1_loss(
                net(hb, args.patch_drop), yt[b].to(DEVICE), beta=0.5)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
    net.eval()
    preds = []
    with torch.no_grad():
        for i in range(0, len(te), 64):
            hb = torch.from_numpy(H[te[i:i + 64]]).float().to(DEVICE)
            preds.append(net(hb).cpu().numpy())
    return np.concatenate(preds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", type=int, default=2)
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--head-lr", type=float, default=1e-3)
    ap.add_argument("--patch-drop", type=float, default=0.25)
    ap.add_argument("--images-dir", default=os.path.join(ROOT, "data", "images"))
    ap.add_argument("--no-nested", action="store_true",
                    help="fixed .5 cut-points (5 fine-tunes instead of 25)")
    args = ap.parse_args()

    from transformers import AutoModel
    base = AutoModel.from_pretrained(MODEL).to(DEVICE).eval()
    n_frozen = base.config.num_hidden_layers - args.blocks

    df = load_dataset()
    y = df["manual_rqi"].values.astype(float)
    yc = df["rqi"].values.astype(int)
    c = S.load_coords(df["image_filename"])
    groups = S.grid_cells(c["lat"].values, c["lon"].values)
    area = c["area"].values

    t0 = time.time()
    H = cache_tokens(df, args.images_dir, n_frozen, base)
    print(f"tokens after block {n_frozen}: {H.shape}  ({time.time() - t0:.0f}s)")

    folds = S.spatial_folds(yc, groups)
    oof = np.zeros(len(y))
    pred = np.zeros(len(y), dtype=int)
    fold_id = np.zeros(len(y), dtype=int)
    for k, (tr, te) in enumerate(folds):
        t0 = time.time()
        oof[te] = train_predict(base, n_frozen, H, y, tr, te, args, S.SEED + k)
        fold_id[te] = k
        th = [1.5, 2.5, 3.5]
        if not args.no_nested:
            ioof = np.zeros(len(y))
            for j, (itr, ite) in enumerate(
                    S.spatial_folds(yc[tr], groups[tr], S.INNER_SPLITS)):
                ioof[tr[ite]] = train_predict(base, n_frozen, H, y, tr[itr],
                                              tr[ite], args, 100 * k + j)
            th = S.tune_thresholds(yc[tr], ioof[tr])
        pred[te] = np.digitize(oof[te], th) + 1
        m = S.ordinal_metrics(yc[te], pred[te], oof[te])
        print(f"  fold {k}: n={len(te)} QWK={m['qwk']:.3f} MAE={m['mae']:.3f} "
              f"AUC={m['bad_auc']:.3f}  th={np.round(th, 2).tolist()} "
              f"[{time.time() - t0:.0f}s]", flush=True)

    res = {"oof": oof, "pred": pred, "fold": fold_id}
    m = S.ordinal_metrics(yc, pred, oof)
    sd = S.per_fold_std(yc, res)
    print(f"\nFine-tune last {args.blocks} blocks, {args.epochs} ep "
          f"({'nested' if not args.no_nested else 'fixed .5'} cut-points):")
    print(f"  QWK={m['qwk']:.3f}±{sd['qwk']:.3f}  MAE={m['mae']:.3f}  "
          f"exact={m['exact']:.3f}  ±1={m['off1']:.3f}  "
          f"bad acc={m['bad_acc']:.3f}  AUC={m['bad_auc']:.3f}")
    for a, label in S.AREA_LABELS.items():
        s = area == a
        ma = S.ordinal_metrics(yc[s], pred[s], oof[s])
        print(f"    {label:22s} QWK={ma['qwk']:.3f} MAE={ma['mae']:.3f} "
              f"AUC={ma['bad_auc']:.3f}")
    np.savez(os.path.join(CACHE, f"oof_ft{args.blocks}.npz"), oof=oof, pred=pred,
             fold=fold_id, files=np.array(df["image_filename"], dtype=object))


if __name__ == "__main__":
    main()
