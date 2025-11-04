"""
Transaction poller CLI commands.

Provides command-line interface for managing the poller,
running manual polls, and viewing metrics.
"""

import asyncio
import sys
from typing import Optional
import structlog

from app.transactions.poller import TransactionPoller
from app.transactions.config import get_poller_config

logger = structlog.get_logger()


def print_status(status: dict):
    """Pretty print poller status."""
    print("\n=== Transaction Poller Status ===\n")
    print(f"Running: {status['running']}")
    print(f"Enabled: {status['enabled']}")
    print(f"Last Poll: {status['last_poll_time'] or 'Never'}")

    print(f"\n--- Circuit Breaker ---")
    cb = status["circuit_breaker"]
    print(f"State: {cb['state']}")
    print(f"Failures: {cb['failure_count']}")
    print(f"Successes: {cb['success_count']}")

    if status["last_run"]:
        print(f"\n--- Last Run ---")
        run = status["last_run"]
        print(f"Run ID: {run['run_id']}")
        print(f"Status: {run['status']}")
        print(f"Duration: {run['duration_seconds']:.2f}s")
        print(f"Fetched: {run['transactions_fetched']}")
        print(f"New: {run['transactions_new']}")
        print(f"Duplicates: {run['transactions_duplicate']}")
        print(f"Stored: {run['transactions_stored']}")
        if run['error_count'] > 0:
            print(f"Errors: {run['error_count']}")

    print(f"\n--- 24 Hour Metrics ---")
    metrics = status["metrics_24h"]
    print(f"Total Runs: {metrics['total_runs']}")
    print(f"Successful: {metrics['successful_runs']}")
    print(f"Failed: {metrics['failed_runs']}")
    print(f"Success Rate: {status['success_rate_24h']:.1%}")
    print(f"Total Transactions: {metrics['total_transactions']}")
    print(f"Avg Duration: {metrics['avg_duration_seconds']:.2f}s")

    print(f"\n--- Configuration ---")
    config = status["config"]
    print(f"Poll Interval: {config['poll_interval_minutes']} minutes")
    print(f"Lookback: {config['lookback_hours']} hours")
    print(f"Batch Size: {config['batch_size']}")
    print(f"Source: {config['source']}")
    print()


def print_metrics(metrics: dict, hours: Optional[int] = None):
    """Pretty print metrics."""
    print(f"\n=== Transaction Poller Metrics ===")
    if hours:
        print(f"(Last {hours} hours)\n")
    else:
        print("(All history)\n")

    agg = metrics["aggregate"]
    print(f"Total Runs: {agg['total_runs']}")
    print(f"Successful: {agg['successful_runs']}")
    print(f"Failed: {agg['failed_runs']}")
    print(f"Partial: {agg['partial_runs']}")
    print(f"Success Rate: {metrics['success_rate']:.1%}")
    print(f"\nTotal Transactions: {agg['total_transactions']}")
    print(f"New Transactions: {agg['total_new_transactions']}")
    print(f"Duplicates: {agg['total_duplicates']}")
    print(f"Errors: {agg['total_errors']}")
    print(f"\nAvg Duration: {agg['avg_duration_seconds']:.2f}s")
    print(f"Avg API Latency: {agg['avg_api_latency_seconds']:.2f}s")
    print(f"Avg Transactions/Run: {agg['avg_transactions_per_run']:.1f}")

    if agg['first_run']:
        print(f"\nFirst Run: {agg['first_run']}")
    if agg['last_run']:
        print(f"Last Run: {agg['last_run']}")
    if agg['last_success']:
        print(f"Last Success: {agg['last_success']}")
    if agg['last_failure']:
        print(f"Last Failure: {agg['last_failure']}")

    if metrics["recent_runs"]:
        print(f"\n--- Recent Runs ---")
        for run in metrics["recent_runs"][:5]:
            print(
                f"{run['started_at']}: {run['status']} - "
                f"{run['transactions_fetched']} fetched, "
                f"{run['transactions_new']} new, "
                f"{run['duration_seconds']:.2f}s"
            )
    print()


async def poll_command():
    """Run a single poll manually."""
    print("Starting manual poll...")
    poller = TransactionPoller()

    try:
        result = await poller.poll_once()
        print(f"\nPoll completed!")
        print(f"Run ID: {result['run_id']}")
        print(f"Status: {result['status']}")
        print(f"Fetched: {result['transactions_fetched']}")
        print(f"New: {result['transactions_new']}")
        print(f"Duplicates: {result['transactions_duplicate']}")
        print(f"Stored: {result['transactions_stored']}")
        if result.get('transactions_failed', 0) > 0:
            print(f"Failed: {result['transactions_failed']}")
        print(f"Duration: {result.get('duration_seconds', 0):.2f}s")
        return 0
    except Exception as e:
        print(f"\nPoll failed: {str(e)}")
        return 1


async def status_command():
    """Show poller status."""
    poller = TransactionPoller()
    status = poller.get_status()
    print_status(status)
    return 0


async def metrics_command(hours: Optional[int] = None):
    """Show poller metrics."""
    poller = TransactionPoller()
    metrics = poller.get_metrics(hours=hours)
    print_metrics(metrics, hours)
    return 0


async def run_command():
    """Run the poller continuously."""
    print("Starting transaction poller...")
    config = get_poller_config()
    print(f"Poll interval: {config.poll_interval_minutes} minutes")
    print(f"Lookback: {config.lookback_hours} hours")
    print(f"Press Ctrl+C to stop\n")

    poller = TransactionPoller()

    try:
        await poller.start()
        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        await poller.stop()
        print("Poller stopped.")
        return 0
    except Exception as e:
        print(f"\nError: {str(e)}")
        await poller.stop()
        return 1


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m app.transactions.cli <command> [options]")
        print("\nCommands:")
        print("  poll              Run a single poll manually")
        print("  status            Show current poller status")
        print("  metrics [hours]   Show metrics (optionally for last N hours)")
        print("  run               Run poller continuously")
        print("\nExamples:")
        print("  python -m app.transactions.cli poll")
        print("  python -m app.transactions.cli status")
        print("  python -m app.transactions.cli metrics 24")
        print("  python -m app.transactions.cli run")
        return 1

    command = sys.argv[1]

    try:
        if command == "poll":
            return asyncio.run(poll_command())
        elif command == "status":
            return asyncio.run(status_command())
        elif command == "metrics":
            hours = int(sys.argv[2]) if len(sys.argv) > 2 else None
            return asyncio.run(metrics_command(hours))
        elif command == "run":
            return asyncio.run(run_command())
        else:
            print(f"Unknown command: {command}")
            return 1
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except Exception as e:
        print(f"Error: {str(e)}")
        logger.exception("cli_error", command=command)
        return 1


if __name__ == "__main__":
    sys.exit(main())
