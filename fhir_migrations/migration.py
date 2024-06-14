"""Migration Module

Captures common methods needed by the system for migration.

When downgrading, the downgrade() function of the currently
applied migration is being run. Downgrade goes 1 step back.
When upgrading, the upgrade() function of the to-be-applied
migration is being run. Upgrade applies all unapplied migrations.

If cycle is present in the migration order, the error is raised,
and manual resolution is necessary.

In order to create a new migration, all existing migrations must
first be applied.

You cannot create more than one new migration file at a time.

For branching/conflict resolution, manually review the migration files.
"""

import configparser
import os
import uuid
import imp
import logging

from fhir_migrations.migration_resource import MigrationManager
from fhir_migrations.utils import LinkedList

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Migration:
    def __init__(self, migrations_dir=None):
        '''Initializes Migration class, which contains the logic
        for managing the migration order'''
        if migrations_dir is None:
            config = configparser.ConfigParser()
            config.read("config.py")
            migrations_dir = config.get("DEFAULT", "MIGRATION_SCRIPTS_DIR", fallback=os.path.join(os.path.dirname(__file__), "versions"))

        self.migrations_dir = migrations_dir
        self.migration_sequence = LinkedList()
        self.migrations_locations = {}
        self.build_migration_sequence()

    def build_migration_sequence(self):
        '''Builds the migration list, based on the double LInked List.
        Checks for cycles'''
        migration_files: list = self.get_migrations()
        migration_nodes: dict = {}

        for migration in migration_files:
            migration_nodes[migration] = self.get_previous_migration_id(migration)

        if len(migration_files) > 0:
            try:
                self.migration_sequence.build_list_from_dictionary(migration_nodes)
            except KeyError as ke:
                logger.error(f"Downrevision migration is missing in the sequence")
                raise ke
            except Exception as e:
                logger.error(f"General exception encountered: {str(e)}")
                raise e
        else:
            error_message = "No valid migration files."
            logger.exception(error_message)


    def get_migrations(self) -> list:
        '''Retrieves all valid migrations from the files in the migration directory.'''
        try:
            migration_files = os.listdir(self.migrations_dir)
            migration_files = [file for file in migration_files if file.endswith('.py')]
        except FileNotFoundError:
            migration_files = []

        revisions = []
        for file_name in migration_files:
            file_path = os.path.join(self.migrations_dir, file_name)
            module_name = os.path.splitext(file_name)[0]
            migration_module = imp.load_source(module_name, file_path)

            # Check for required attributes and methods
            if not hasattr(migration_module, "revision"):
                raise RuntimeError(f"Migration '{file_name}' is missing 'revision' variable.")
            if not hasattr(migration_module, "down_revision"):
                raise RuntimeError(f"Migration '{file_name}' is missing 'down_revision' variable.")
            if not hasattr(migration_module, "upgrade") or not callable(getattr(migration_module, "upgrade")):
                raise RuntimeError(f"Migration '{file_name}' is missing 'upgrade' method.")
            if not hasattr(migration_module, "downgrade") or not callable(getattr(migration_module, "downgrade")):
                raise RuntimeError(f"Migration '{file_name}' is missing 'downgrade' method.")

            revision = str(getattr(migration_module, "revision"))
            if revision:
                revisions.append(revision)
                self.migrations_locations[revision] = module_name

        return revisions

    def get_previous_migration_id(self, migration_id: str) -> str:
        """Retrieve the down_revision from a migration script.
        Revision variables are used to track the migration order."""
        try:
            filename = self.migrations_locations[migration_id] + ".py"
        except KeyError as e:
            message = f"No corresponding file found for migration {migration_id}"
            logger.error(message)
            raise ValueError(message)

        down_revision = None
        migration_path = os.path.join(self.migrations_dir, filename)
        if os.path.exists(migration_path):
            try:
                migration_module = imp.load_source("migration_module", migration_path)
                down_revision = getattr(migration_module, "down_revision", None)
            except Exception as e:
                message = f"Error loading migration script {filename}: {e}"
                logger.error(message)
                raise e
        else:
            message = f"Migration script {filename} does not exist."
            logger.info(message)

        return down_revision

    def generate_migration_script(self, migration_name: str):
        """Generate a new migration script with basic functions."""
        self.build_migration_sequence()
        if migration_name in self.migrations_locations.values():
            message = f"That name already exist. Use a new name for the migration"
            logger.error(message)

            raise ValueError(message)

        current_migration_id = str(self.get_latest_applied_migration_from_fhir())
        latest_created_migration_id = str(self.get_latest_created_migration())

        if current_migration_id != latest_created_migration_id:
            message = f"There exists not applied migration."
            logger.error(message)

            raise RuntimeError(message)

        new_id = str(uuid.uuid4())
        migration_filename = f"{migration_name}.py"
        migration_path = os.path.join(self.migrations_dir, migration_filename)

        with open(migration_path, "w") as migration_file:
            migration_file.write(f"# Migration script generated for {migration_name}\n")
            migration_file.write(f"revision = '{new_id}'\n")
            migration_file.write(f"down_revision = '{current_migration_id}'\n")
            migration_file.write("\n")
            migration_file.write("def upgrade():\n")
            migration_file.write("    # Add your upgrade migration code here\n")
            migration_file.write("    print('upgraded')\n")
            migration_file.write("\n")
            migration_file.write("def downgrade():\n")
            migration_file.write("    # Add your downgrade migration code here\n")
            migration_file.write("    print('downgraded')\n")
            migration_file.write("\n")

        logger.info(f"Generated new migration {migration_name}")

        return migration_filename

    def run_migrations(self, direction: str):
        """Run migrations based on the specified direction ("upgrade" or "downgrade")."""
        # Update the migration to acquire most recent updates in the system
        self.build_migration_sequence()
        if direction not in ["upgrade", "downgrade"]:
            raise ValueError("Invalid migration direction. Use 'upgrade' or 'downgrade'.")

        current_migration = self.get_latest_applied_migration_from_fhir()
        if current_migration and self.migration_sequence.find(current_migration) is None:
            message = f"Applied migration {current_migration} does not exist in the migration system"
            logger.error(message)

            raise KeyError(message)

        applied_migrations = None
        unapplied_migrations = None
        if direction == "upgrade":
            unapplied_migrations = self.get_unapplied_migrations(current_migration)
        elif direction == "downgrade" and current_migration is not None:
            applied_migrations = self.get_previous_migration(current_migration)
            unapplied_migrations = current_migration

        if not unapplied_migrations or unapplied_migrations == 'None':
            # If no migrations are left to run, silently exit
            return

        if direction == "upgrade":
            # Run all available migrations
            for migration in unapplied_migrations:
                self.run_migration(direction, migration, migration)
        if direction == "downgrade":
            # Run one migration down
            self.run_migration(direction, unapplied_migrations, applied_migrations)

    def run_migration(self, direction: str, next_migration: str, applied_migration: str):
        """Run migration(s) based on the specified direction ("upgrade" or "downgrade")."""
        # Update the migration to acquire most recent updates in the system
        migration_path = os.path.join(self.migrations_dir, self.migrations_locations[next_migration] + ".py")
        try:
            logger.info("Running the migration")
            migration_module = imp.load_source('migration_module', migration_path)

            if direction == "upgrade":
                migration_module.upgrade()
            elif direction == "downgrade":
                migration_module.downgrade()

            self.update_latest_applied_migration_in_fhir(applied_migration)
        except Exception as e:
            message = f"Error executing migration {applied_migration}: {e}"
            logger.error(message)

    def get_unapplied_migrations(self, applied_migration) -> list:
        """Retrieve all migrations that have not yet been ran."""
        return self.migration_sequence.get_sublist(applied_migration)

    def get_previous_migration(self, current_migration) -> str:
        """Retrieve the previous migration."""
        return self.migration_sequence.previous(current_migration)

    def get_latest_created_migration(self) -> str:
        """Retrieve the latest created migration."""
        return self.migration_sequence.head

    ## FHIR MANAGEMENT LOGIC
    def get_latest_applied_migration_from_fhir(self) -> str:
        """Retrieve the latest applied migration migration id from FHIR."""
        # Logic to retrieve the latest applied migration number from FHIR
        manager = MigrationManager.get_manager(create_if_not_found=False)
        if manager is None:
            return None

        return manager.get_latest_migration()

    def update_latest_applied_migration_in_fhir(self, latest_applied_migration: str):
        """Update the latest applied migration id in FHIR."""
        # Logic to update the latest applied migration number in FHIR
        manager = MigrationManager.get_manager(create_if_not_found=True)
        manager.update_migration(latest_applied_migration)
