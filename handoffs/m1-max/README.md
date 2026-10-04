# M1 Max validation handoff

`3dgen-mac-starter.zip` contains the personal 3DGen prototype source, locked Node dependencies manifest, Mac setup/build/benchmark scripts, a synthetic robot reference PNG and the measured RTX 3090 baseline. It is a source kit, not a built or signed Mac application.

SHA-256: `b56796e39cff223c8530d733fcc93b25adc47bba03678f00747f5b7f022cbc0d`

Size: 440,473 bytes. No API credentials, session descriptors, model weights, installed dependencies or private runtime state are included. The 29 KB procedural GLB under `demo-history` is an automated-test fixture.

Extract the archive, then read `3dgen-studio/docs/MAC-VALIDATION.md`. The desired machine is Apple M1 Max with 64 GB unified memory. Native Metal setup and app execution have not yet been verified on that machine.

Core commands, from the extracted `3dgen-studio` directory:

```bash
python3 tools/setup-mac.py --plan
bash Setup-Mac.command
bash Benchmark-Mac.command
bash Build-Mac.command
```

The issue linked to this handoff defines prerequisites, pinned revisions, acceptance checks and the result comment to return. Keep reports and fixes tied to that issue. Do not substitute cloud generation for the local Metal benchmark.
