import time

from app import create_app
from app.services.recon_runner import claim_next_run, execute_run


def main() -> None:
    app = create_app()
    with app.app_context():
        while True:
            run_id = claim_next_run()
            if run_id is None:
                time.sleep(2)
                continue
            execute_run(run_id)


if __name__ == "__main__":
    main()
