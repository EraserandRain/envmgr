from __future__ import annotations

if __package__:
    from .scaffold import ScaffoldError, generate_role
else:  # pragma: no cover - compatibility when run as a script
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.scaffold import ScaffoldError, generate_role


def main() -> None:
    role_name = input("Enter role name: ").strip()
    try:
        generate_role(role_name)
    except FileExistsError:
        print(f"Role '{role_name}' already exists.")
        return
    except (FileNotFoundError, ScaffoldError) as error:
        print(error)
        return

    print(f"Role '{role_name}' generated successfully.")


if __name__ == "__main__":
    main()
