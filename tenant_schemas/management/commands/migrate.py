from django.conf import settings
from django.db import connection
from south.exceptions import NoMigrations
from south import migration
from south.migration.base import Migrations
from south.management.commands.migrate import Command as MigrateCommand
from tenant_schemas.management.commands import SyncCommon
from tenant_schemas.utils import get_tenant_model, get_public_schema_name


class Command(SyncCommon):
    help = "Migrate schemas with South"
    option_list = MigrateCommand.option_list + SyncCommon.option_list

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        if self.sync_public:
            self.migrate_public_apps()
        if self.sync_tenant:
            self.migrate_tenant_apps(self.schema_name)

    def _save_south_settings(self):
        self._old_south_modules = None
        if hasattr(settings, "SOUTH_MIGRATION_MODULES") and settings.SOUTH_MIGRATION_MODULES is not None:
            self._old_south_modules = settings.SOUTH_MIGRATION_MODULES.copy()
        else:
            settings.SOUTH_MIGRATION_MODULES = dict()

    def _restore_south_settings(self):
        settings.SOUTH_MIGRATION_MODULES = self._old_south_modules

    def _clear_south_cache(self):
        for mig in list(migration.all_migrations()):
            delattr(mig._application, "migrations")
        Migrations._clear_cache()

    def _migrate(self, apps, tenant=None):
        if tenant:
            connection.set_tenant(tenant, include_public=False)

        if self.args:
            if self.args[0] in apps:
                MigrateCommand().execute(*self.args, **self.options)
            return

        for app in apps:
            try:
                apps = [Migrations(app)]
            except NoMigrations:
                continue
            else:
                MigrateCommand().execute(app=app, *self.args, **self.options)

    def migrate_tenant_apps(self, schema_name=None):
        self._save_south_settings()

        apps = self.tenant_apps or self.installed_apps

        if schema_name:
            self._notice("=== Running migrate for schema: %s" % schema_name)
            connection.set_schema_to_public()
            tenant = get_tenant_model().objects.get(schema_name=schema_name)
            self._migrate(apps, tenant)
        else:
            all_tenants = get_tenant_model().objects.exclude(schema_name=get_public_schema_name())
            if not all_tenants:
                self._notice("No tenants found")

            for tenant in all_tenants:
                Migrations._dependencies_done = False  # very important, the dependencies need to be purged from cache
                self._notice("=== Running migrate for schema %s" % tenant.schema_name)
                self._migrate(apps, tenant)

        self._restore_south_settings()

    def migrate_public_apps(self):
        self._save_south_settings()

        apps = self.shared_apps or self.installed_apps

        self._notice("=== Running migrate for schema public")
        self._migrate(apps)

        self._clear_south_cache()
        self._restore_south_settings()
