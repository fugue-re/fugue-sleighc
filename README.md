# fugue-sleighc

Wrapper around Ghidra's SLEIGH specification compiler.

## Requirements

- Bison (>= 3.8)
- Flex (>= 2.6)
- zlib (>= 1.2.12)

## Nix

The `flake.nix` exposes the bundled `sleighc` binary and a development shell
with the build prerequisites. Because the C/C++ sources live in a git
submodule (`vendored/`), invocations must opt in with `?submodules=1`:

```sh
nix build .?submodules=1            # builds packages.default (sleighc)
nix develop .?submodules=1          # dev shell with bison, cmake, flex, zlib, sleighc
```

The package version is read from `Cargo.toml`, so no Nix file needs editing
when bumping Ghidra releases.
