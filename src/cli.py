"""Flask CLI commands for Amoja Social Manager."""

import click

from src.services import auth as auth_service


def register_cli(app):
    """Register application CLI commands."""

    @app.cli.command("create-owner")
    @click.option(
        "--username",
        envvar="AUTH_USERNAME",
        prompt="Username",
        help="Owner username (3-64 lowercase letters, digits, . _ -).",
    )
    @click.option(
        "--password",
        envvar="AUTH_PASSWORD",
        prompt="Password",
        hide_input=True,
        confirmation_prompt=True,
        help="Owner password (12-128 characters).",
    )
    def create_owner(username, password):
        """Create the single private owner account."""
        try:
            created = auth_service.provision_owner(username, password)
        except auth_service.AuthValidationError as exc:
            raise click.ClickException(str(exc)) from exc
        except Exception as exc:
            db_error = "Is the database migrated? Run: make migrate"
            raise click.ClickException(f"Owner setup failed. {db_error}") from exc

        if created:
            click.echo("Owner account created.")
        else:
            click.echo("Owner already exists; credentials unchanged.")
