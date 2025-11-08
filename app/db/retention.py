"""Data retention and archival utilities."""

import structlog
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.db.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


class RetentionPolicy:
    """
    Manages data retention and archival policies.

    Implements cleanup of old emails, logs, and other data according
    to configured retention periods.
    """

    def __init__(self):
        """Initialize retention policy manager."""
        self.default_email_retention_days = 30
        self.default_log_retention_days = 90

    async def cleanup_old_emails(
        self, days: Optional[int] = None, dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Clean up old emails that exceed retention period.

        Args:
            days: Retention period in days (defaults to config or 30)
            dry_run: If True, only count what would be deleted

        Returns:
            Dictionary with cleanup results
        """
        async with UnitOfWork() as uow:
            # Get retention period from config or use default
            if days is None:
                days = await uow.config.get_value(
                    "retention.email_days", self.default_email_retention_days
                )

            # Ensure days is an int
            days = int(days) if days is not None else self.default_email_retention_days

            # Get old emails
            old_emails = await uow.emails.get_old_emails(days)
            count = len(old_emails)

            logger.info(
                "cleanup_old_emails",
                days=days,
                count=count,
                dry_run=dry_run,
            )

            if not dry_run and count > 0:
                # Delete old emails
                deleted = 0
                for email in old_emails:
                    try:
                        await uow.emails.delete(email.id)
                        deleted += 1
                    except Exception as e:
                        logger.error(
                            "error_deleting_email",
                            email_id=email.id,
                            error=str(e),
                        )

                await uow.commit()

                return {
                    "action": "cleanup_emails",
                    "days": days,
                    "found": count,
                    "deleted": deleted,
                    "dry_run": False,
                }

            return {
                "action": "cleanup_emails",
                "days": days,
                "found": count,
                "deleted": 0,
                "dry_run": dry_run,
            }

    async def cleanup_old_logs(
        self, days: Optional[int] = None, dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Clean up old log entries that exceed retention period.

        Args:
            days: Retention period in days (defaults to config or 90)
            dry_run: If True, only count what would be deleted

        Returns:
            Dictionary with cleanup results
        """
        async with UnitOfWork() as uow:
            # Get retention period from config or use default
            if days is None:
                days = await uow.config.get_value(
                    "retention.log_days", self.default_log_retention_days
                )

            # Ensure days is an int
            days = int(days) if days is not None else self.default_log_retention_days

            logger.info(
                "cleanup_old_logs",
                days=days,
                dry_run=dry_run,
            )

            if not dry_run:
                deleted = await uow.logs.cleanup_old_logs(days)
                await uow.commit()

                return {
                    "action": "cleanup_logs",
                    "days": days,
                    "deleted": deleted,
                    "dry_run": False,
                }

            # Dry run - count what would be deleted using repository
            from datetime import timedelta

            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            # Use repository count method with comparison operator
            count = await uow.logs.count(timestamp__lt=cutoff)

            return {
                "action": "cleanup_logs",
                "days": days,
                "found": count,
                "deleted": 0,
                "dry_run": True,
            }

    async def archive_old_matches(
        self, days: int = 180, dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Archive old match records (future implementation).

        This could move old matches to a separate archive table or
        export them to cold storage.

        Args:
            days: Age threshold for archival
            dry_run: If True, only count what would be archived

        Returns:
            Dictionary with archival results
        """
        logger.info(
            "archive_old_matches",
            days=days,
            dry_run=dry_run,
            status="not_implemented",
        )

        return {
            "action": "archive_matches",
            "days": days,
            "archived": 0,
            "dry_run": dry_run,
            "status": "not_implemented",
        }

    async def run_all_policies(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Run all retention policies.

        Args:
            dry_run: If True, only report what would be done

        Returns:
            Dictionary with results from all policies
        """
        logger.info("run_all_retention_policies", dry_run=dry_run)

        email_result = await self.cleanup_old_emails(dry_run=dry_run)
        log_result = await self.cleanup_old_logs(dry_run=dry_run)
        # match_result = await self.archive_old_matches(dry_run=dry_run)

        return {
            "emails": email_result,
            "logs": log_result,
            # "matches": match_result,
            "dry_run": dry_run,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


async def run_retention_cleanup(dry_run: bool = True):
    """
    Convenience function to run retention cleanup.

    Args:
        dry_run: If True, only report what would be done
    """
    policy = RetentionPolicy()
    results = await policy.run_all_policies(dry_run=dry_run)

    print("\n" + "=" * 60)
    print("RETENTION POLICY CLEANUP RESULTS")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"Timestamp: {results['timestamp']}")
    print()

    if "emails" in results:
        email_data = results["emails"]
        print("Emails:")
        print(f"  - Retention period: {email_data['days']} days")
        if "found" in email_data:
            print(f"  - Found: {email_data['found']}")
        if "deleted" in email_data:
            print(f"  - Deleted: {email_data['deleted']}")

    if "logs" in results:
        log_data = results["logs"]
        print("\nLogs:")
        print(f"  - Retention period: {log_data['days']} days")
        if "found" in log_data:
            print(f"  - Found: {log_data['found']}")
        if "deleted" in log_data:
            print(f"  - Deleted: {log_data['deleted']}")

    print("\n" + "=" * 60)

    return results


if __name__ == "__main__":
    import asyncio
    import sys

    dry_run = "--live" not in sys.argv
    if not dry_run:
        response = input(
            "WARNING: This will permanently delete data. Continue? (yes/no): "
        )
        if response.lower() != "yes":
            print("Cancelled.")
            sys.exit(0)

    asyncio.run(run_retention_cleanup(dry_run=dry_run))
