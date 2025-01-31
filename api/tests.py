import json

from django.test import TransactionTestCase
from django.core.exceptions import MultipleObjectsReturned
from django.contrib.auth import get_user_model
#from django.contrib.auth.models import Group
from django.contrib.auth.hashers import make_password
from django.utils import timezone as django_timezone
from django.test import Client

from html.parser import HTMLParser


class CSRFParser(HTMLParser):
    csrfmiddlewaretoken = ''
    def handle_starttag(self, tag, attrs):
        if tag == 'input':
            kwargs = dict(attrs)
            if set(['type', 'name', 'value']) <= set(kwargs.keys()) and kwargs['name'] == 'csrfmiddlewaretoken':
                self.csrfmiddlewaretoken = kwargs['value']
                #print("Encountered a start tag:", tag, kwargs)


class Usr(TransactionTestCase):
    'User test case'
    maxDiff = None
    reset_sequences = True
    csrfmiddlewaretoken = ''

    def setUp(self):
        self.test_password = 't0#e9@s8$t7'
        self.user = get_user_model()(username=f'test_{int(django_timezone.now().timestamp())}', password=make_password(self.test_password), email='test@test.test', first_name='Test', last_name='tesT', is_staff=True, is_active=True, is_superuser=True)
        self.user.save()
        #self.user.groups.add(Group.objects.get(id=1))
        print(self.user.id, self.user, self.test_password)
        print()

        self.client = Client()
        url = '/admin/login/'
        print('⚽GET', url)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        print(self.client.cookies)
        parser = CSRFParser()
        parser.feed(response.content.decode('utf-8'))
        self.csrfmiddlewaretoken = parser.csrfmiddlewaretoken
        print('csrfmiddlewaretoken', self.csrfmiddlewaretoken)
        self.login()

    def tearDown(self):
        self.client.logout()
        self.user.delete()

    def login(self):
        print()
        url = '/api/login/'
        data = json.dumps({'username':self.user.username, 'password':self.test_password})
        print('⚽POST', url, data)# headers={"host": "127.0.0.1:8000"}
        response = self.client.post(url, data, 'json', headers={'X-CSRFToken':self.csrfmiddlewaretoken})
        self.assertEqual(response.status_code, 200)
        print(self.client.cookies)
        print('Request♥', response.request)
        print('Response♡', json.dumps(response.json(), ensure_ascii=False).encode('utf-8'))
        print(response.content)

    def test_products(self):
        print()
        url = '/api/products/'
        print('⚽GET', url)
        response = self.client.get(url, headers={'X-CSRFToken':self.csrfmiddlewaretoken})
        self.assertEqual(response.status_code, 200)
        print('Request♥', response.request)
        print('Response♡', response, response.headers)
        print('DATA⋆', eval(json.loads(response.content)))
        print()
        url = '/api/products/cash/'
        print('⚽GET', url)
        response = self.client.get(url, headers={'X-CSRFToken':self.csrfmiddlewaretoken})
        self.assertEqual(response.status_code, 200)
        print('Request♥', response.request)
        print('Response♡', response, response.headers)
        print('DATA⋆', eval(json.loads(response.content)))

    def test_docs(self):
        print()
        url = '/api/docs/'
        print('⚽GET', url)
        response = self.client.get(url, headers={'X-CSRFToken':self.csrfmiddlewaretoken})
        self.assertEqual(response.status_code, 200)
        print('Request♥', response.request)
        print('Response♡', response, response.headers)
        print('DATA⋆', eval(json.loads(response.content.decode('utf8').replace('null', 'None'))))
        print()
        url = '/api/doc/cash/'
        data = json.dumps({'sum_final':1000, 'records':[{'product':1, 'count':10, 'price':45}, {'product':2, 'count':10, 'price':63}]})
        print('⚽POST', url, data)
        response = self.client.post(url, data, 'json', headers={'X-CSRFToken':self.csrfmiddlewaretoken})
        self.assertEqual(response.status_code, 200)
        print('Request♥', response.request)
        print('Response♡', response, response.headers)
        print('DATA⋆', json.loads(response.content))
