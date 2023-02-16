from copy import deepcopy
from datetime import datetime, timedelta
from functools import reduce

from django.db.models import Func, Q, IntegerField, CharField, FloatField
from django.db.models.functions import Concat
from django.utils import timezone
from operator import __or__ as OR
from operator import __and__ as AND
from pytz import timezone as pytz_timezone

from .constants import CustomAttributePresentations
from .dates import Dates
from .util import make_list, normalize_field


CHAR = [
    'CharField', 'BinaryField', 'FileField', 'FilePathField', 'IPAddressField',
    'GenericIPAddressField', 'SlugField', 'TextField', 'UUIDField'
]

INT = [
    'AutoField', 'BigAutoField', 'BooleanField', 'DecimalField', 'DurationField', 'FloatField',
    'IntegerField', 'BigIntegerField', 'PositiveIntegerField', 'PositiveSmallIntegerField',
    'SmallIntegerField'
]

DATE = [
    'DateField', 'DateTimeField', 'TimeField'
]

OTHER = [
    'BooleanField', 'NullBooleanField', 'OneToOneField'
]


class FormatDigit(Func):
    function = 'LPAD'
    template = "%(function)s(%(expressions)s, 2, '0')"
    output_field = CharField()


class CastFloat(Func):
    function = 'CAST'
    template = "%(function)s(%(expressions)s as DECIMAL(20,5))"
    output_field = FloatField()


class Filter(object):

    def __init__(self, model, tz='UTC', **kwargs):
        self.db_model = model
        self.original_model = model.objects
        extra_filters = kwargs.get('extra_filters')

        # Caso seja o model "Contact", devo ignorar os "excluídos" (ContactStatus.DELETED == 3)
        if self.original_model.model._meta.model_name == 'contact':
            self.original_model = self.original_model.exclude(status=3)

        # Case seja o model "Card", devo ignorar os "arquivados"
        elif self.original_model.model._meta.model_name == 'card':
            self.original_model = self.original_model.exclude(archived=1)

        if extra_filters:
            self.original_model = self.original_model.filter(**extra_filters)

        # Não pode ter ordenação:
        # https://docs.djangoproject.com/en/1.9/topics/db/aggregation/
        # interaction-with-default-ordering-or-order-by
        self.original_model = self.original_model.order_by()

        self.model = deepcopy(self.original_model)
        self.now = timezone.now().replace(tzinfo=pytz_timezone(tz))
        self.tz = tz
        self.date_start = None
        self.date_end = None
        self.annotated_fields = []
        self.annotation_period = []
        self.annotation_select = []
        self.model_fields = model._meta._forward_fields_map
        self.working_model = None

    def reset(self):
        self.model = deepcopy(self.original_model)

    def change_timezone(self, tz):
        self.tz = tz

    def filter_by_custom_field(self, field):
        custom = field.split('custom_attributes__')[-1]
        field = '{}_custom_attributes__value'.format(
            self.model.model._meta.model_name
        )
        self.filter_by('custom_attributes__name={}'.format(custom))

    def filter_by_date(self, date_field, date_start=None, date_end=None, **kwargs):
        if kwargs.get('period') and hasattr(Dates, kwargs['period']):
            period = getattr(Dates(self.tz), kwargs['period'])
            self.date_start, self.date_end = period()
        else:
            self.date_start = date_start or self.date_start
            self.date_end = date_end or self.date_end

            if self.date_start:
                self.date_start = self.date_start.replace(tzinfo=pytz_timezone(self.tz))
            if self.date_end:
                self.date_end = self.date_end.replace(tzinfo=pytz_timezone(self.tz))

        # Garantir que a data de inicio é anterior a data de fim
        if self.date_start and self.date_end and self.date_start > self.date_end:
            self.date_start, self.date_end = self.date_end, self.date_start

        if type(date_field) != str:
            return

        if date_field.endswith('generated_creation_date'):
            related_model = ''
            related_date_field = date_field.split('__')
            if len(related_date_field) > 1:
                related_model = '{}__'.format(related_date_field[0])

            if self.date_start:
                self.model = self.model.annotate(
                    period=Concat(
                        '{}period_ym'.format(related_model),
                        '{}period_d'.format(related_model),
                        '{}period_h'.format(related_model),
                        output_field=IntegerField()
                    )
                ).filter(period__gte=self.date_start.strftime('%Y%m%d%H'))
            if self.date_end:
                self.model = self.model.annotate(
                    period=Concat(
                        '{}period_ym'.format(related_model),
                        '{}period_d'.format(related_model),
                        '{}period_h'.format(related_model),
                        output_field=IntegerField()
                    )
                ).filter(period__lte=self.date_end.strftime('%Y%m%d%H'))
            self.annotation_select.append('period')

        else:
            if self.date_start:
                date_start = {'{}__{}'.format(date_field, 'gte'): self.date_start}
                self.model = self.model.filter(**date_start)

            if self.date_end:
                date_end = {'{}__{}'.format(date_field, 'lte'): self.date_end}
                self.model = self.model.filter(**date_end)

    def get_Q(self, filter_by_conditions, logical_operator=None, apply_dates=True):
        """
        {
            "logical_operator": "AND",
            "rules": [
                {
                    "logical_operator": "OR",
                    "rules": [
                        {
                            "field": "email",
                            "operator": "istartswith",
                            "value": "teste"
                        },
                        {
                            "field": "name",
                            "operator": "contains",
                            "value": "teste"
                        }
                    ]
                },
                {
                    "logical_operator": "AND",
                    "rules": [
                        {
                            "field": "email_status",
                            "operator": "exact",
                            "value": "1"
                        },
                        {
                            "field": "optin",
                            "operator": "exact",
                            "value": "1"
                        }
                    ]
                }
            ]
        }
        """
        filter_list = []

        if 'logical_operator' in filter_by_conditions:
            return self.get_Q(
                filter_by_conditions['rules'],
                filter_by_conditions['logical_operator'],
                apply_dates
            )

        for rule in filter_by_conditions:
            _filter = {}

            if 'logical_operator' in rule:
                if rule.get('rules'):
                    get_Q = self.get_Q(rule['rules'], rule['logical_operator'], apply_dates)
                    if get_Q:
                        filter_list.append(get_Q)
            else:

                field = rule['field']
                operator = rule.get('operator', 'in')
                value = rule.get('value', 0)
                if value is None:
                    value = 0
                _type = rule.get('type', 'abc')

                if not field:
                    continue

                if not (
                    field.startswith('custom_attributes__') or
                    field.endswith('generated_creation_date')
                ):

                    if '__' in field:
                        details = field.split('__')
                        related_model = details[0]
                        related_field = details[1]
                        related_model = self.db_model._meta.get_field(related_model)
                        field_ = related_model.related_model._meta.get_field(
                            related_field
                        )
                    else:
                        field_ = self.db_model._meta.get_field(field)

                    field_type = field_.get_internal_type()
                    if field_type in CHAR:
                        _type = 'abc'

                    if field_type in INT:
                        _type = '123'

                    elif field_type in DATE:
                        _type = 'date'

                if not (operator and field):
                    continue

                negate = operator.startswith('not_')
                coalesce = False

                # Caso "is (not)? empty"
                if operator == 'isnull':
                    coalesce = True

                if operator in ['in', 'not_in'] and not value:
                    continue

                if _type == 'date' and not apply_dates:
                    continue

                if value == 'Blank':
                    negate = operator == 'not_exact'
                    operator = 'exact'
                    value = ''

                elif value == 'Null':
                    value = (operator == 'exact')
                    operator = 'isnull'
                    negate = False

                if negate:
                    operator = operator.replace('not_', '')

                if field == 'birthdate':
                    now = datetime.now(pytz_timezone(self.tz))
                    if operator == 'today':
                        filter_list += [
                            Q(**{'{}__month'.format(field): now.month}),
                            Q(**{'{}__day'.format(field): now.day})
                        ]

                    elif operator == 'this_month':
                        filter_list.append(Q(**{'{}__month'.format(field): now.month}))

                    elif 'age' in operator:
                        operator = operator.split('_')[1]
                        if operator == 'range':
                            try:
                                min_type = value.get('min_value').get('type')
                                max_type = value.get('max_value').get('type')
                                min_value = value.get('min_value').get('value')
                                max_value = value.get('max_value').get('value')
                                if not (min_type or max_type or min_value or max_value):
                                    continue
                            except AttributeError:
                                continue
                        else:
                            if not (value.get('type') and value.get('value')):
                                continue

                        d1, d2 = Dates(self.tz).age(value, operator)
                        if operator in ['range', 'exact']:
                            operator = 'range'
                            filter_list += [
                                Q(**{'{}__{}'.format(field, operator): [d1, d2]})
                            ]
                        elif operator == 'gte':
                            filter_list += [
                                Q(**{'{}__{}'.format(field, operator): d1})
                            ]
                        elif operator == 'lte':
                            filter_list += [
                                Q(**{'{}__{}'.format(field, operator): d2})
                            ]
                    else:
                        method = getattr(Dates(self.tz), operator)
                        d1, d2 = method()
                        filter_list += [
                            Q(**{'{}__month__range'.format(field): [d1.month, d2.month]}),
                            Q(**{'{}__day__range'.format(field): [d1.day, d2.day]})
                        ]

                    continue

                elif _type == 'date' and hasattr(Dates, operator) and apply_dates and not coalesce:
                    method = getattr(Dates(self.tz, False), operator)
                    value = method()
                    operator = 'range'

                elif _type == 'date' and 'age' in operator:
                    operator = operator.split('_')[1]
                    if operator == 'range':
                        try:
                            min_type = value.get('min_value').get('type')
                            max_type = value.get('max_value').get('type')
                            min_value = value.get('min_value').get('value')
                            max_value = value.get('max_value').get('value')
                            if not (min_type or max_type or min_value or max_value):
                                continue
                        except AttributeError:
                            continue
                    else:
                        if not (value.get('type') and value.get('value')):
                            continue

                    value = Dates(self.tz).age(value, operator)

                    if operator == 'exact':
                        operator = 'range'

                    elif operator == 'gte':
                        value = value[0]

                    elif operator == 'lte':
                        value = value[1]

                elif _type == 'date' and apply_dates and not coalesce:
                    try:
                        value = timezone.now() - timedelta(days=int(value))
                    except ValueError:
                        if len(value) > 10:
                            value = datetime.strptime(value, '%Y-%m-%d')
                        else:
                            value = datetime.strptime(value, '%Y-%m-%d').date()

                            if operator == 'gt':
                                value = value + timedelta(days=(1))
                                operator = 'gte'

                            elif operator == 'lte':
                                value = value + timedelta(days=1)
                                operator = 'lt'

                    except Exception:
                        pass

                    # Desconsiderar horário
                    if operator == 'exact':
                        if len(str(value)) > 10:
                            value = value.date()
                        operator = 'startswith'

                if field.startswith('custom_attributes__'):
                    if value is True:
                        value = 'true'
                    elif value is False:
                        value = 'false'
                    custom = field.split('custom_attributes__')[-1]
                    custom_field = '{}_custom_attributes__value'.format(
                        self.working_model.model._meta.model_name
                    )

                    null_list = [pk for pk in self.working_model.filter(**{
                        'custom_attributes__name': custom,
                        '{}'.format(custom_field): ''
                    }).values_list('pk', flat=True)]

                    is_checkbox = self.working_model.filter(
                        custom_attributes__name=custom,
                        custom_attributes__presentation_id=CustomAttributePresentations.CHECKBOX
                    )

                    if is_checkbox and value == 'false':

                        false_list = [pk for pk in self.working_model.filter(**{
                            'custom_attributes__name': custom,
                            '{}__{}'.format(custom_field, operator): value
                        }).values_list('pk', flat=True)]

                        _filter.update({
                            'pk__in': [pk for pk in self.working_model.exclude(
                                custom_attributes__name=custom
                            ).values_list('pk', flat=True)] + false_list or [0]
                        })

                    elif operator == 'isnull' and value:
                        if value == "true":
                            _filter.update({
                                'pk__in': [pk for pk in self.working_model.exclude(
                                    custom_attributes__name=custom
                                ).values_list('pk', flat=True)] + null_list or [0]
                            })
                        else:
                            _filter.update({
                                'pk__in': [pk for pk in self.working_model.filter(
                                    custom_attributes__name=custom
                                ).values_list('pk', flat=True) if pk not in null_list] or [0]
                            })

                    else:

                        if _type == 'date':
                            if type(value) == str:
                                value = f'{value}'[:19]

                            elif type(value) == tuple:
                                start_date, end_date = value
                                start_date = f'{start_date}'[:19]
                                end_date = f'{end_date}'[:19]
                                value = (start_date, end_date)

                        elif operator in ['lte', 'gte']:
                            value = CastFloat(value)

                        working_model = self.working_model.filter(**{
                            'custom_attributes__name': custom,
                            '{}__{}'.format(custom_field, operator): value
                        })

                        ids = set(working_model.values_list(
                            'pk', flat=True
                        ))
                        null_list = set(null_list)
                        pks = list(ids.difference(null_list))

                        _filter.update({
                            'pk__in': pks or [0]
                        })

                elif field.endswith('generated_creation_date'):
                    related_model = ''
                    related_date_field = field.split('__')
                    if len(related_date_field) > 1:
                        related_model = '{}__'.format(related_date_field[0])

                    if type(value) == tuple:
                        date_start, date_end = value
                        if date_start:
                            annotate = {
                                '{}period'.format(related_model): Concat(
                                    '{}period_ym'.format(related_model),
                                    FormatDigit('{}period_d'.format(related_model)),
                                    FormatDigit('{}period_h'.format(related_model)),
                                    output_field=IntegerField()
                                )
                            }
                            self.working_model = self.working_model.annotate(
                                **annotate
                            )
                            _filter.update({
                                '{}period__{}'.format(
                                    related_model, 'gte'
                                ): date_start.strftime('%Y%m%d%H')
                            })

                        if date_end:
                            annotate = {
                                '{}period'.format(related_model): Concat(
                                    '{}period_ym'.format(related_model),
                                    FormatDigit('{}period_d'.format(related_model)),
                                    FormatDigit('{}period_h'.format(related_model)),
                                    output_field=IntegerField()
                                )
                            }
                            self.working_model = self.working_model.annotate(
                                **annotate
                            )
                            _filter.update({
                                '{}period__{}'.format(
                                    related_model, 'lte'
                                ): date_end.strftime('%Y%m%d%H')
                            })
                    else:
                        annotate = {
                            '{}period'.format(related_model): Concat(
                                '{}period_ym'.format(related_model),
                                FormatDigit('{}period_d'.format(related_model)),
                                FormatDigit('{}period_h'.format(related_model)),
                                output_field=IntegerField()
                            )
                        }
                        self.working_model = self.working_model.annotate(
                            **annotate
                        )
                        _filter.update({
                            '{}period__{}'.format(
                                related_model, operator
                            ): value.strftime('%Y%m%d%H')
                        })

                    self.annotation_select.append(f'{related_model}period')
                    self.annotation_period.append(f'{related_model}period')

                # Verifico se devo comparar valores vazios
                elif operator == 'isnull' and coalesce:
                    if _type in ['123', 'date']:
                        _filter = Q(**{'{}__isnull'.format(field): True})
                    else:
                        _filter = (Q(**{'{}__isnull'.format(field): True}) | Q(**{field: ''}))

                    if not value:  # is not empty
                        _filter = ~(_filter)

                    filter_list.append(_filter)
                    continue

                else:
                    _filter['{}__{}'.format(field, operator)] = value

                # Se o field relacionado é o model reverso para os contato
                # aplico filtro no status sem o ContactStatus.DELETED == 3
                if field.startswith('contacts__') and field != 'contacts__status':
                    _filter['contacts__status__in'] = [1, 2]

                if negate:
                    filter_list.append(~Q(**_filter))
                else:
                    filter_list.append(Q(**_filter))

        if not filter_list:
            return

        if logical_operator == 'AND':
            conditions = reduce(AND, filter_list)
        else:
            conditions = reduce(OR, filter_list)

        return conditions

    def filter_by(self, filter_by_conditions, queryset=None, apply_dates=True, report=False):
        if not self.working_model:
            self.working_model = deepcopy(self.model)
            self.overrided = True

        if queryset:
            self.working_model = queryset

        if not filter_by_conditions:
            return self.working_model.filter(pk=0) if not report else self.working_model

        if type(filter_by_conditions) is dict:
            _filter = self.get_Q(filter_by_conditions, apply_dates=apply_dates)
            if _filter:
                self.working_model = self.working_model.filter(_filter)

        else:
            self.filtered_by = {}
            for _filter in make_list(filter_by_conditions.split(',')):
                condition, value = _filter.split('=')
                self.filtered_by[condition] = value

            self.working_model = self.working_model.filter(**self.filtered_by)

        # Clear period annotations to fix distinct query problem
        self.clean_annotation_period()

        if getattr(self, 'overrided', False):
            self.model = self.working_model
            return self.model

        return self.working_model

    def clean_annotation_period(self):
        for annotation in self.annotation_period:
            self.working_model.query.annotations.pop(annotation, None)
        self.annotation_period = []

    def clean_annotation_select(self):
        if self.annotation_select:
            for annotation in self.annotation_select:
                self.working_model.query.annotation_select.pop(annotation, None)
            self.working_model.query.set_group_by()

    def ordered_by(self, *order):
        self.model = self.model.order_by(*order)

    def limit(self, start=None, end=None):
        self.model = self.model[start:end]

    def fields(self, *field_names):
        self.model = self.model.values(*field_names)

    def distinct(self, field):
        if field.startswith('custom_attributes__'):
            self.filter_by_custom_field(field)
            field = '{}_custom_attributes__value'.format(
                self.model.model._meta.model_name
            )

        fields = self.model.order_by().values_list(field, flat=True).distinct()
        return sorted([normalize_field(field) for field in fields if field is not None])

    def list(self):
        return self.model.all()

    def list_id(self):
        return self.model.objects.values_list('id', flat=True)

    def total(self):
        return self.model.count()

    def annotate(self, fields, filter_custom=True):
        for field in make_list(fields):
            if field.startswith('custom_attributes__'):
                if filter_custom:
                    self.filter_by_custom_field(field)

                field = '{}_custom_attributes__value'.format(
                    self.model.model._meta.model_name
                )

            if field not in self.annotated_fields:
                self.annotated_fields.append(field)
