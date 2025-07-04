# Databricks notebook source
# MAGIC %pip install -U databricks-sdk==0.36.0
# MAGIC %restart_python

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors.platform import NotFound
import pyspark.sql.functions as F

class NestedNamespace:

    def __init__(self, dictionary: dict = None, prefix=None):
        prefix = prefix + '.' if prefix else ''
        self.__setattr_direct('dictionary', dictionary or dict())
        self.__setattr_direct('prefix', prefix)
        self.__setattr_direct('iterator', None)

    def __getattr__(self, name):
        name = self.prefix + name
        return self.dictionary.get(name, NestedNamespace(dictionary=self.dictionary, prefix=name))

    def __setattr__(self, name, value):
        name = self.prefix + name
        self.dictionary[name] = value

        # since we've overwritten the node in the tree, prune branch by deleting any children/ancestors
        name += '.'
        children = [k for k in filter(lambda x: x.startswith(name), self.dictionary.keys())]
        for k in children:
            del(self.dictionary[k])

    # bypass overridden behaviour to directly set attributes
    def __setattr_direct(self, name, value):
        super().__setattr__(name, value)

    def __repr__(self):
        args = [f"{key}='{self[key]}'" for key in self]
        return f"{self.__class__.__name__} ({', '.join(args)})" if args else ""

    def __iter__(self):
        self.__setattr_direct(
            'iterator',
            filter(
                lambda x: x.startswith(self.prefix),
                iter(self.dictionary)
            )
        )

        return self

    def __next__(self):
        return next(self.iterator).removeprefix(self.prefix) if self.iterator else None

    def __getitem__(self, name):
        return self.__getattr__(name)

    def __setitem__(self, name, value):
        return self.__setattr__(name, value)

class DBAcademyHelper(NestedNamespace):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.workspace = WorkspaceClient()

        try:
            default_catalog = self.workspace.settings.default_namespace.get().namespace.value
        except:
            default_catalog = 'dbacademy'

        meta = f'{default_catalog}.ops.meta'
        catalog = None
        schema = None

        # query the metadata table and populate self with key/values
        for row in spark.sql(f'SELECT key,value FROM {meta}').collect():
            setattr(self, row['key'], row['value'])

            if row['key'] == 'catalog_name':
                catalog = row['value']
            elif row['key'] == 'schema_name':
                schema = row['value']

        # set default catalog and schema according to metadata
        if catalog:
            spark.sql(f'USE CATALOG {catalog}')

            if schema:
                spark.sql(f'USE SCHEMA {schema}')

    @classmethod
    def add_init(cls, function_ref):
        try:
            initializers = getattr(cls, '_initializers')
        except AttributeError:
            initializers = list()

        initializers += [function_ref]
        setattr(cls, '_initializers', initializers)
        return function_ref

    @classmethod
    def add_method(cls, function_ref):
        setattr(cls, function_ref.__name__, function_ref)
        return function_ref

    def init(self):
        for key in self:
            value = self[key]
            if value and type(value) == str:
                try:
                    spark.conf.set(f'DA.{key}', value)
                    spark.conf.set(f'da.{key}', value)
                except:
                    pass

        try:
            for i in getattr(self.__class__, '_initializers'):
                i(self)
        except AttributeError:
            pass

    def print_copyrights(self):
        datasets = self.datasets
        for i in datasets:
            catalog = datasets[i].split('.')[0]
            description = spark.sql(
                f'DESCRIBE CATALOG {catalog}'
            ).where(
                F.col('info_name') == 'Comment'
            ).select(
                'info_value'
            ).collect()[0]['info_value']
            print(description)

    def workspace_find(self, item_type: str, value: str=None, member: str='name', api: str='list'):
        method = getattr(getattr(self.workspace, item_type), api)
        for item in method():
            if getattr(item, member) == value:
                return item

    def unique_name(self, sep: str) -> str:
        return self.pseudonym.replace(' ', sep)