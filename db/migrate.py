import os

from dotenv import load_dotenv
from yoyo import get_backend, read_migrations

load_dotenv()

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")


def main() -> None:
    backend = get_backend(os.environ["DATABASE_URL"])
    migrations = read_migrations(MIGRATIONS_DIR)
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))


if __name__ == "__main__":
    main()
