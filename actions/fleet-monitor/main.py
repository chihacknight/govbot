import json
import sys
from pathlib import Path

import click
import yaml

sys.path.append(str(Path(__file__).parent))

from fleet_config import read_fleet


@click.group()
def cli():
    """Fleet monitor: observability for the govbot scraper and data-repo fleets."""


@cli.command("list-fleet")
@click.option(
    "--config-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=True,
    help="Directory holding pipeline-manager config YAMLs and their templates/ folder.",
)
def list_fleet(config_dir: Path):
    """Print one JSON Lines jurisdiction record per locale per fleet."""
    try:
        records = read_fleet(config_dir)
    except (ValueError, yaml.YAMLError) as e:
        raise click.ClickException(str(e)) from e
    for record in records:
        click.echo(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    cli(auto_envvar_prefix="FLEET_MONITOR")
