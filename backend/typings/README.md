Type stubs for pyright only (`pyrightconfig.json`, `stubPath` = this folder).
Heavy or optional third-party packages (torch, numpy, PIL, cv2, …) are typed as
`Any` here, so the check gives the same result on a dev machine with torch and in
the torch-free CI. Runtime imports are unaffected.
