import logging, sys
from decimal import Decimal
from io import BytesIO, StringIO
from datetime import datetime, timedelta
try:
    from zoneinfo import available_timezones, ZoneInfo
except:
    from backports.zoneinfo import available_timezones, ZoneInfo

from django.utils import timezone as django_timezone
from django.utils.translation import gettext as _
from django.utils.html import format_html, format_html_join
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.contrib import admin, messages
from django import forms
from django.http import StreamingHttpResponse, FileResponse, HttpResponseRedirect
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.db.models import F, Q, Min, Max, Sum, Value, Count, IntegerField, TextField, CharField, OuterRef, Subquery
from django.db.models.query import QuerySet
from django.db import connections
from django.contrib.admin.models import LogEntry
from django.contrib.admin.widgets import AutocompleteSelect
from django.shortcuts import render
from django.views.generic.edit import FormView
from django.core.cache import caches
from django.conf import settings
from django.apps import apps as django_apps

from .models import Doc, Record, Register
from users.models import User

def get_model(app_model):
    app_name, model_name = app_model.split('.')
    return django_apps.get_app_config(app_name).get_model(model_name)


class DropDownFilter(admin.SimpleListFilter):
    template = 'dropdown_filter_from_memory.html'


class UploadFileForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    file = forms.FileField(widget=forms.ClearableFileInput(attrs={'allow_multiple_selected': True}))


class CustomModelAdmin(admin.ModelAdmin):

    def logi(self, *args):
        msg = f'ℹ️{self.__class__.__name__}.{sys._getframe().f_back.f_code.co_name}'
        for arg in args:
            msg += f'::{arg}'
        logging.info(msg)

    def logw(self, *args):
        msg = f'⚠{self.__class__.__name__}.{sys._getframe().f_back.f_code.co_name}'
        for arg in args:
            msg += f'::{arg}'
        logging.warning(msg)

    def loge(self, err, *args):
        msg = f'🆘{self.__class__.__name__}.{err.__traceback__.tb_frame.f_code.co_name}::{err}::LINE={err.__traceback__.tb_lineno}'
        for arg in args:
            msg += f'::{arg}'
        logging.error(msg)


class DocAdmin(CustomModelAdmin):
    list_display = ('id', 'created_at', 'registered_at', 'get_records', 'get_sum_cost', 'get_sum_price', 'sum_final', 'owner', 'contractor', 'type', 'tax', 'author', 'extinfo')
    list_display_links = ('id', 'created_at', 'registered_at')
    search_fields = ('id', 'created_at', 'registered_at', 'owner__name', 'contractor__name', 'type__name', 'tax__name', 'sale_point__name', 'author__username', 'extinfo')

    def save_model(self, request, instance, form, change):
        current_user = request.user
        instance = form.save(commit=False)
        if not change or not instance.author:
            instance.author = current_user
        instance.save()
        form.save_m2m()
        return instance

    def get_records(self, obj):
        try:
            idxs = Record.objects.filter(doc=obj).annotate(admin_path_prefix=Value(settings.ADMIN_PATH_PREFIX, CharField())).values_list('admin_path_prefix', 'product_id', 'product__name')
        except Exception as e:
            self.loge(e)
            return ''
        else:
            if not idxs:
                return ''
            content = format_html_join('\n', '<p><font color="green" face="Verdana, Geneva, sans-serif"><a href="{0}/refs/product/?id={1}" target="_blank">{2}</a></font></p>', idxs)
            return format_html('<details><summary>{}</summary>{}</details>', idxs[0][2], content)
    get_records.short_description = _('Products')

    def get_sum_cost(self, obj):
        full_sum = 0
        try:
            full_sum = Record.objects.filter(doc=obj).aggregate(full_sum=Sum(F('count')*F('cost')))['full_sum']
        except Exception as e:
            self.loge(e)
        else:
            if full_sum:
                full_sum = full_sum.quantize(Decimal('0.00'))
            else:
                full_sum = 0
        return format_html('<font color="green" face="Verdana, Geneva, sans-serif">{}</font>', full_sum)
    get_sum_cost.short_description = _('sum cost')

    def get_sum_price(self, obj):
        full_sum = 0
        try:
            full_sum = Record.objects.filter(doc=obj).aggregate(full_sum=Sum(F('count')*F('price')))['full_sum']
        except Exception as e:
            self.loge(e)
        else:
            if full_sum:
                full_sum = full_sum.quantize(Decimal('0.00'))
            else:
                full_sum = 0
        return format_html('<font color="green" face="Verdana, Geneva, sans-serif">{}</font>', full_sum)
    get_sum_price.short_description = _('sum price')

admin.site.register(Doc, DocAdmin)


class RecordAdmin(CustomModelAdmin):
    list_display = ('id', 'get_product', 'get_cost', 'get_price', 'get_count', 'get_sum_cost', 'get_sum_price', 'doc', 'extinfo')
    list_display_links = ('id',)
    search_fields = ('id', 'doc__owner__name', 'doc__contractor__name', 'doc__type__name', 'doc__tax__name', 'doc__sale_point__name', 'doc__author__username', 'extinfo')

    def get_product(self, obj):
        return format_html('<a href="{}/refs/product/?id={}" target="_blank">{}</a>', settings.ADMIN_PATH_PREFIX, obj.product.id, obj.product.name)
    get_product.short_description = _('product')

    def get_count(self, obj):
        color = 'green' if obj.doc.type.income==True else 'red'
        return format_html('<font color="{}" face="Verdana, Geneva, sans-serif">{}</font>', color, obj.count)
    get_count.short_description = _('count')
    get_count.admin_order_field = 'count'

    def get_cost(self, obj):
        return format_html('<font color="green" face="Verdana, Geneva, sans-serif">{} {}</font>', obj.cost.quantize(Decimal('0.00')), obj.currency.name if obj.currency else '')
    get_cost.short_description = _('cost')
    get_cost.admin_order_field = 'cost'

    def get_price(self, obj):
        return format_html('<font color="green" face="Verdana, Geneva, sans-serif">{} {}</font>', obj.price.quantize(Decimal('0.00')), obj.currency.name if obj.currency else '')
    get_price.short_description = _('price')
    get_price.admin_order_field = 'price'

    def get_sum_cost(self, obj):
        return format_html('<font color="green" face="Verdana, Geneva, sans-serif">{} {}</font>', (obj.cost*obj.count).quantize(Decimal('0.00')), obj.currency.name if obj.currency else '')
    get_sum_cost.short_description = _('sum price')

    def get_sum_price(self, obj):
        return format_html('<font color="green" face="Verdana, Geneva, sans-serif">{} {}</font>', (obj.price*obj.count).quantize(Decimal('0.00')), obj.currency.name if obj.currency else '')
    get_sum_price.short_description = _('sum price')

admin.site.register(Record, RecordAdmin)


class RegisterAdmin(CustomModelAdmin):
    list_display = ('id', 'rec', 'get_product', 'get_cost', 'get_price', 'get_count', 'get_sum_cost', 'get_sum_price', 'get_doc')
    list_display_links = ('id',)
    search_fields = ('id', 'rec__doc__owner__name', 'rec__doc__contractor__name', 'rec__doc__type__name')
    list_filter = ('rec__product', 'rec__doc', 'rec__doc__type')

    def get_product(self, obj):
        return format_html('<a href="{}/refs/product/?id={}" target="_blank">{}</a>', settings.ADMIN_PATH_PREFIX, obj.rec.product.id, obj.rec.product.name)
    get_product.short_description = _('product')

    def get_count(self, obj):
        color = 'green' if obj.rec.doc.type.income==True else 'red'
        return format_html('<font color="{}" face="Verdana, Geneva, sans-serif">{}</font>', color, obj.rec.count)
    get_count.short_description = _('count')

    def get_cost(self, obj):
        return format_html('<font color="green" face="Verdana, Geneva, sans-serif">{} {}</font>', obj.rec.cost.quantize(Decimal('0.00')), obj.rec.currency.name if obj.rec.currency else '')
    get_cost.short_description = _('cost')

    def get_price(self, obj):
        return format_html('<font color="green" face="Verdana, Geneva, sans-serif">{} {}</font>', obj.rec.price.quantize(Decimal('0.00')), obj.rec.currency.name if obj.rec.currency else '')
    get_price.short_description = _('price')

    def get_doc(self, obj):
        return format_html('<font color="green" face="Verdana, Geneva, sans-serif">{}</font>', obj.rec.doc)
    get_doc.short_description = _('document')

    def get_sum_cost(self, obj):
        return format_html('<font color="green" face="Verdana, Geneva, sans-serif">{} {}</font>', (obj.rec.cost*obj.rec.count).quantize(Decimal('0.00')), obj.rec.currency.name if obj.rec.currency else '')
    get_sum_cost.short_description = _('sum cost')

    def get_sum_price(self, obj):
        return format_html('<font color="green" face="Verdana, Geneva, sans-serif">{} {}</font>', (obj.rec.price*obj.rec.count).quantize(Decimal('0.00')), obj.rec.currency.name if obj.rec.currency else '')
    get_sum_price.short_description = _('sum price')

admin.site.register(Register, RegisterAdmin)
