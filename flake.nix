{
  description = "Wrapper around Ghidra's SLEIGH specification compiler";

  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixos-25.05";

  outputs =
    { self, nixpkgs }:
    let
      supportedSystems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;

      cargoToml = builtins.fromTOML (builtins.readFile ./Cargo.toml);

      buildDeps =
        pkgs: with pkgs; [
          bison
          cmake
          flex
          zlib
        ];

      mkSleighc =
        pkgs:
        pkgs.stdenv.mkDerivation {
          pname = "sleighc";
          version = cargoToml.package.version;
          src = ./vendored;
          cmakeFlags = [
            "-DCMAKE_INSTALL_LIBDIR=lib"
            "-DBUILD_COMPILER=ON"
            "-DBUILD_DECOMPILER=OFF"
          ];
          buildInputs = buildDeps pkgs;
        };
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          sleighc = mkSleighc pkgs;
        in
        {
          inherit sleighc;
          default = sleighc;
        }
      );

      devShells = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        {
          default = pkgs.mkShell {
            name = "sleighc-dev";
            buildInputs =
              (buildDeps pkgs)
              ++ [
                pkgs.git
                self.packages.${system}.sleighc
              ];
          };
        }
      );
    };
}
