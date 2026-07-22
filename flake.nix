{
  description = "FastAPI dev shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }: {
    devShells.x86_64-linux.default =
      let
        pkgs = import nixpkgs {
          system = "x86_64-linux";
        };

        python = pkgs.python312;

        pythonEnv = python.withPackages (ps: with ps; [
          fastapi
          uvicorn
          sqlalchemy
          psycopg2
          python-jose
          cryptography
          passlib
          bcrypt
          pydantic
          email-validator
          python-dotenv
          python-multipart
          openpyxl
          pandas
          apscheduler
        ]);
      in
      pkgs.mkShell {
        packages = [
          pythonEnv
        ];
      };
  };
}
