// Hungarian texts for the RQI model card. Pure, so the exact wording the owner
// sees (and which number gets which label) is pinned by unit tests.
import type { RqiModelInfo } from './types'

export interface ModelCardStat {
  label: string
  value: string
  hint: string
}

const pct = (v?: number | null) => (v == null ? '–' : `${(v * 100).toFixed(1)}%`)
const num = (v?: number | null, d = 3) => (v == null ? '–' : v.toFixed(d))

/** True when the numbers come from the honest spatial evaluation (ml/model_card.json). */
export const isSpatial = (info: RqiModelInfo): boolean => info.metricsSource === 'spatial_cv'

/**
 * The stat tiles, best-known first. `badSign` + `badFrom` describe the bad-road
 * threshold on the canonical scale (e.g. "≤", 3).
 */
export const modelCardStats = (info: RqiModelInfo, badSign: string, badFrom: number): ModelCardStat[] => {
  if (!info.available) return []
  const spatial = isSpatial(info)
  const seg = info.segmentLengthM != null ? Math.round(info.segmentLengthM) : 200
  const head: ModelCardStat[] = spatial
    ? [
        {
          label: 'Új helyszíneken mért pontosság (QWK)',
          value: num(info.qwk),
          hint: 'képkockánként, olyan utcákon, amelyeket a modell sosem látott (1 = tökéletes)',
        },
        {
          label: `Útszakaszon (${seg} m, QWK)`,
          value: num(info.segmentQwk),
          hint: 'a térképen látható szakaszok szintjén',
        },
        {
          label: 'Teljesen új régióban (QWK)',
          value: num(info.newAreaQwk),
          hint: 'egy egész gyűjtési területet kihagyva a tanításból',
        },
      ]
    : [{ label: 'QWK', value: num(info.qwk), hint: 'sorrendi egyezés (1 = tökéletes)' }]
  return [
    ...head,
    { label: 'Pontos találat', value: pct(info.exactAcc), hint: 'ahányszor eltalálja az osztályzatot' },
    { label: 'Átl. hiba (MAE)', value: num(info.mae), hint: 'átlagos eltérés osztályzatban' },
    { label: 'Jó/rossz döntés', value: pct(info.badRoadAcc), hint: `rossz út (RQI${badSign}${badFrom}) felismerése` },
    { label: 'Rossz-út AUC', value: num(info.badRoadAuc), hint: 'megkülönböztető képesség' },
    { label: 'Tanítókép', value: info.nTrain != null ? String(info.nTrain) : '–', hint: 'címkézett kép a modellben' },
  ]
}

/** The caption under the tiles: where the numbers come from. */
export const metricsNote = (info: RqiModelInfo): string =>
  isSpatial(info)
    ? 'Új helyszíneken mért pontosság: a számok térben csoportosított keresztvalidációból ' +
      'származnak (1 km-es cellák), vagyis olyan utcákon mérve, amelyeket a modell a tanításkor ' +
      `sosem látott${info.metricsMeasuredOn ? ` (mérve: ${info.metricsMeasuredOn})` : ''}.`
    : 'A számok a modellfájl saját metaadataiból származnak (régebbi, véletlen ' +
      'keresztvalidáció) – ismert helyeken mérve, ezért optimisták lehetnek.'
