import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.etl.run_once import run_once

log = logging.getLogger(__name__)


def main() -> None: 
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run_once,
        CronTrigger(minute=5),
        max_instances=1,
        coalesce=True,
    )
    log.info("first run on startup")
    run_once()
    log.info("scheduler started: every hour at HH:05 UTC")
    scheduler.start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()