import copy
import datetime as dt
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error

spec=importlib.util.spec_from_file_location('deals', Path(__file__).parents[1]/'scripts/update_deals.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
NOW=dt.datetime(2026,10,19,13,tzinfo=dt.timezone.utc)
# Synthetic tests only. Never published and no actual price/model claim.
def product(**changes):
    p=dict(sku=123456,name='SYNTHETIC TEST TOY',manufacturer='LEGO',modelNumber='TEST-ONLY',
        salePrice=20,regularPrice=40,onSale=True,onlineAvailability=True,condition='New',
        priceRestriction=None,url='https://www.bestbuy.com/site/test/123456.p',
        image='https://pisces.bbystatic.com/image2/test.jpg',categoryPath=[{'name':'Toys & Games'}],
        details=[{'name':'Recommended Minimum Age','value':'6 years'}])
    p.update(changes);return p
class Validation(unittest.TestCase):
    def test_good_offer(self):
        d=m.normalize(product(),NOW)
        self.assertEqual((d['discount'],d['savings'],d['age']),(50,20,6))
    def test_reject_untrustworthy_offers(self):
        for change in [dict(onlineAvailability=False),dict(onSale=False),dict(condition='Open Box'),
            dict(priceRestriction='MAP'),dict(manufacturer='Unknown'),dict(salePrice='NaN'),
            dict(salePrice=-1),dict(salePrice=40),dict(salePrice=30.01),dict(regularPrice=4,salePrice=2),
            dict(categoryPath=[{'name':'Video Games'}]),dict(details=[]),dict(sku='bad'),
            dict(url='https://www.bestbuy.com.evil.test/item'),dict(image='https://evil.test/x.jpg')]:
            with self.subTest(change=change):self.assertIsNone(m.normalize(product(**change),NOW))
    def test_age_evidence(self):
        for value in ['18 years','18 months','2 years','under 3 years','adult','unknown']:
            self.assertIsNone(m.minimum_age([{'name':'Recommended Minimum Age','value':value}]))
        self.assertEqual(m.minimum_age([{'name':'Recommended Age','value':'Ages 3+'}]),3)
    def test_exact_discount_threshold(self):
        self.assertIsNotNone(m.normalize(product(salePrice=30),NOW))
        self.assertIsNone(m.normalize(product(salePrice=30.001),NOW))
    def test_deduplicate_and_cap(self):
        rows=[product(sku=i) for i in range(150)]
        self.assertEqual(len(m.select(rows+rows,NOW)),100)
    def test_empty_success_replaces_expired_offers(self):
        self.assertEqual(m.select([],NOW),[])
    def test_cache_age_and_future(self):
        for hours,expected in [(24,True),(47,True),(48,False),(73,False),(-1,False)]:
            old={'last_success':m.stamp(NOW-dt.timedelta(hours=hours)),'source_products':[product()]}
            self.assertEqual(m.fresh_state(old,NOW) is not None,expected)
    def test_escaping(self):
        d=m.normalize(product(name='<script>alert(1)</script>'),NOW)
        c=m.card(d,NOW);self.assertNotIn('<script>',c);self.assertIn('&lt;script&gt;',c)
    def test_bad_schema_is_failure(self):
        with self.assertRaises(ValueError):m.discover('SECRET',fetch=lambda u:{'products':None})
    def test_pagination(self):
        calls=[]
        def fetch(url):
            calls.append(url);return {'products':[product(sku=len(calls))],'totalPages':2}
        self.assertEqual(len(m.discover('SECRET',fetch,lambda t:None)),2)
        self.assertEqual(len(calls),2)
    def test_key_not_leaked(self):
        def fail(*args,**kwargs):
            raise urllib.error.HTTPError('https://example.test/?apiKey=SECRET',401,'SECRET',{},None)
        with self.assertRaises(RuntimeError) as caught:m.get_json('https://example.test',opener=fail)
        self.assertNotIn('SECRET',str(caught.exception))
    def test_rate_limit_retry(self):
        attempts=[]
        def fail(*args,**kwargs):
            attempts.append(1);raise urllib.error.HTTPError('x',429,'secret',{'Retry-After':'1'},None)
        with self.assertRaises(RuntimeError):m.get_json('https://example.test',opener=fail,sleeper=lambda t:None)
        self.assertEqual(len(attempts),3)
    def test_template_preserves_brand_and_filters(self):
        template=(Path(__file__).parents[1]/'templates/site.html').read_text()
        page=m.render(template,None,'Awaiting authorization',NOW,'test-1')
        for value in ['vintage-theme','id="search"','id="category"','id="age-filter"','id="favorites"','tbc-build','Toy Bargain Club']:
            self.assertTrue(value in page, value)
        self.assertNotIn('<!--DEAL_',page)
        self.assertNotIn('All 15 products',page)
if __name__=='__main__':unittest.main()
