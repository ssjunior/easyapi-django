from .tenant import db_state


class DBRouter:
    def db_for_read(self, model, **hints):
        if model._meta.app_config.label == 'master':
            account_db = 'master'
        elif model._meta.app_config.label == 'queue':
            account_db = 'queue'
        else:
            account_db = db_state.get()

        # print(f'Database for read {account_db} {model.__module__}\n')
        return account_db

    def db_for_write(self, model, **hints):
        if model._meta.app_config.label == 'master':
            account_db = 'master'
        elif model._meta.app_config.label == 'queue':
            account_db = 'queue'
        else:
            account_db = db_state.get()

        # print(f'Database for write {account_db} {model.__module__}\n')
        return account_db

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        should_migrate = False

        if app_label == 'master':
            should_migrate = db == 'master'
        elif app_label == 'queue':
            should_migrate = db == 'queue'
        else:
            if db == 'default':
                should_migrate = True

        return should_migrate
