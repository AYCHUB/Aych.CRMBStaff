# coding: utf-8
"""
Test cases for Lead module
@author: Sébastien Renard (sebastien.renard@digitalfox.org)
@license: AGPL v3 or newer (http://www.gnu.org/licenses/agpl-3.0.html)
"""

from django.test import TestCase, override_settings
from django.core import urlresolvers
from django.test import RequestFactory
from django.contrib.messages.storage import default_storage
from django.contrib.auth.models import Group, User


from people.models import Consultant
from leads.models import Lead
from staffing.models import Mission
from crm.models import Subsidiary, BusinessBroker, Client
from core.tests import PYDICI_FIXTURES, setup_test_user_features, TEST_USERNAME, PREFIX
from leads import learn as leads_learn
from leads.utils import postSaveLead
import pydici.settings


from urllib2 import urlparse
import os.path
from decimal import Decimal
from datetime import date, datetime


class LeadModelTest(TestCase):
    fixtures = PYDICI_FIXTURES

    def setUp(self):
        setup_test_user_features()
        self.test_user = User.objects.get(username=TEST_USERNAME)
        if not os.path.exists(pydici.settings.DOCUMENT_PROJECT_PATH):
            os.makedirs(pydici.settings.DOCUMENT_PROJECT_PATH)

    def test_create_lead(self):
        self.client.force_login(self.test_user)
        lead = create_lead()
        self.failUnlessEqual(lead.staffing.count(), 0)
        self.failUnlessEqual(lead.staffing_list(), ", (JCF)")
        lead.staffing.add(Consultant.objects.get(pk=1))
        self.failUnlessEqual(lead.staffing.count(), 1)
        self.failUnlessEqual(len(lead.update_date_strf()), 14)
        self.failUnlessEqual(lead.staffing_list(), "SRE, (JCF)")
        self.failUnlessEqual(lead.short_description(), "A wonderfull lead th...")
        self.failUnlessEqual(urlresolvers.reverse("leads:detail", args=[4]), PREFIX + "/leads/4/")

        url = "".join(urlparse.urlsplit(urlresolvers.reverse("leads:detail", args=[4]))[2:])
        response = self.client.get(url)
        self.failUnlessEqual(response.status_code, 200)
        context = response.context[-1]
        self.failUnlessEqual(unicode(context["lead"]), u"World company : DSI  - laala")
        self.failUnlessEqual(unicode(context["user"]), "sre")

    def test_save_lead(self):
        subsidiary = Subsidiary.objects.get(pk=1)
        broker = BusinessBroker.objects.get(pk=1)
        client = Client.objects.get(pk=1)
        lead = Lead(name="laalaa",
          state="QUALIF",
          client=client,
          salesman=None,
          description="A wonderfull lead that as a so so long description",
          subsidiary=subsidiary)
        deal_id = client.organisation.company.code, date.today().strftime("%y")
        self.assertEqual(lead.deal_id, "")  # No deal id code yet
        lead.save()
        self.assertEqual(lead.deal_id, "%s%s01" % deal_id)
        lead.paying_authority = broker
        lead.save()
        self.assertEqual(lead.deal_id, "%s%s01" % deal_id)
        lead.deal_id = ""
        lead.save()
        self.assertEqual(lead.deal_id, "%s%s02" % deal_id)  # 01 is already used

    def test_save_lead_and_active_client(self):
        lead = Lead.objects.get(id=1)
        lead.state = "LOST"
        lead.save()
        lead = Lead.objects.get(id=1)
        self.assertTrue(lead.client.active)  # There's still anotger active lead for this client
        otherLead = Lead.objects.get(id=3)
        otherLead.state = "SLEEPING"
        otherLead.save()
        lead = Lead.objects.get(id=1)
        self.assertFalse(lead.client.active)
        newLead = Lead()
        newLead.subsidiary_id = 1
        newLead.client = lead.client
        newLead.save()
        lead = Lead.objects.get(id=1)
        self.assertTrue(lead.client.active)  # A new lead on this client should mark it as active again

    def test_lead_done_work(self):
        for i in (1, 2, 3):
            lead = Lead.objects.get(id=i)
            a, b = lead.done_work()
            c, d = lead.done_work_k()
            e = lead.unused()
            f = lead.totalObjectiveMargin()
            for x in (a, b, c, d, e, f):
                self.assertIsInstance(x, (int, float, Decimal))

    def test_checkDoc(self):
        for i in (1, 2, 3):
            lead = Lead.objects.get(id=i)
            lead.checkDeliveryDoc()
            lead.checkBusinessDoc()

class LeadLearnTestCase(TestCase):
    """Test lead state proba learn"""
    fixtures = PYDICI_FIXTURES

    def test_state_model(self):
        if not leads_learn.HAVE_SCIKIT:
            return
        r1 = Consultant.objects.get(id=1)
        r2 = Consultant.objects.get(id=2)
        c1 = Client.objects.get(id=1)
        c2 = Client.objects.get(id=1)
        for i in range(20):
            a = create_lead()
            if a.id%2:
                a.state = "WON"
                a.sales = a.id
                a.client= c1
                a.responsible = r1
            else:
                a.state = "FORGIVEN"
                a.sales = a.id
                a.client = c2
                a.responsible = r2
            a.save()
        leads_learn.eval_state_model()
        self.assertGreater(leads_learn.test_state_model(), 0.8, "Proba is too low")

    def test_tag_model(self):
        if not leads_learn.HAVE_SCIKIT:
            return
        for lead in Lead.objects.all():
            lead.tags.add("coucou")
            lead.tags.add("camembert")
        self.assertGreater(leads_learn.test_tag_model(), 0.8, "Probal is too low")


    def test_too_few_lead(self):
        lead = create_lead()
        f = RequestFactory()
        request = f.get("/")
        request.user = User.objects.get(id=1)
        request.session = {}
        request._messages = default_storage(request)
        lead = create_lead()
        postSaveLead(request, lead, [], sync=True)  # Learn model cannot exist, but it should not raise error


    def test_mission_proba(self):
        for i in range(5):
            # Create enough data to allow learn model to exist
            a = create_lead()
            a.state="WON"
            a.save()
        lead = Lead.objects.get(id=1)
        lead.state="LOST"  # Need more than one target class to build a solver
        lead.save()
        f = RequestFactory()
        request = f.get("/")
        request.user = User.objects.get(id=1)
        request.session = {}
        request._messages = default_storage(request)
        lead = create_lead()
        lead.state = "OFFER_SENT"
        lead.save()
        postSaveLead(request, lead, [], sync=True)
        mission = lead.mission_set.all()[0]
        if leads_learn.HAVE_SCIKIT:
            self.assertEqual(mission.probability, lead.stateproba_set.get(state="WON").score)
        else:
            self.assertEqual(mission.probability, 50)
        lead.state = "WON"
        lead.save()
        postSaveLead(request, lead, [], sync=True)
        mission = Mission.objects.get(id=mission.id)  # reload it
        self.assertEqual(mission.probability, 100)


class LeadNextcloudTagTestCase(TestCase):
    """Test lead tag on nextcloud file"""
    fixtures = PYDICI_FIXTURES

    def setUp(self):
        """Create the nextcloud file tables with init datas"""
        from core.utils import getLeadDirs
        from leads.utils import connect_to_nextcloud_db
        connection = None
        try:
            connection = connect_to_nextcloud_db()
            create_nextcloud_tag_database(connection)
            cursor = connection.cursor()

            # Create test data files for the 3 test leads
            create_file = u"INSERT INTO oc_filecache (fileid, path, name, path_hash, mimetype) VALUES (%s, %s, %s, %s, 6)"
            for i in range(1, 3):
                lead = Lead.objects.get(id=i)
                (client_dir, lead_dir, business_dir, input_dir, delivery_dir) = getLeadDirs(lead, with_prefix=False)
                # Create 6 files per lead, 2 in each lead directory
                # With <file_id> like <lead_id> in first digit, and <file_id> in second digit
                files = [
                    (i*10+1, delivery_dir+u"test1.txt", u"test1.txt", i*10+1),
                    (i*10+2, delivery_dir+u"test2.txt", u"test2.txt", i*10+2),
                    (i*10+3, business_dir+u"test3.txt", u"test3.txt", i*10+3),
                    (i*10+4, business_dir+u"test4.txt", u"test4.txt", i*10+4),
                    (i*10+5, input_dir+u"test5.txt",    u"test5.txt", i*10+5),
                    (i*10+6, input_dir+u"test6.txt",    u"test6.txt", i*10+6)
                ]
                cursor.executemany(create_file, files)
            connection.commit()
        finally:
            if connection:
                connection.close()

    def test_tag_and_remove_tag_file(self):
        # TODO
        from leads.utils import connect_to_nextcloud_db, tag_leads_files, remove_lead_tag, merge_lead_tag
        connection = None
        try:
            connection = connect_to_nextcloud_db()
            cursor = connection.cursor()

            lead = Lead.objects.get(id=1)
            lead.tags.add("A test tag")
            lead.tags.add("Another tag")
            # Make it into a clean sorted list
            lead_tags = list(lead.tags.all().values_list('name', flat=True))
            lead_tags.sort()

            # The function to be tested
            tag_leads_files([lead])

            # Test the 6 lead file tags
            get_file_tag_names = u"SELECT st.name " \
                                 u"FROM oc_systemtag_object_mapping om " \
                                 u"INNER JOIN oc_systemtag st ON st.id = om.systemtagid " \
                                 u"WHERE om.objectid = %s"

            cursor.execute(get_file_tag_names, (11, ))
            file_tags = cursor.fetchall()

            # Format into a sorted list
            actual_file_lead_tags = [i[0] for i in file_tags]
            actual_file_lead_tags.sort()

            self.assertEqual(lead_tags, actual_file_lead_tags)
        finally:
            if connection:
                connection.close()


def create_lead():
    """Create test lead
    @return: lead object"""
    lead = Lead(name="laala",
          due_date=date(2008,11,01),
          update_date=datetime(2008, 11, 1, 15,55,40),
          creation_date=datetime(2008, 11, 1, 15,43,43),
          start_date=date(2008, 11, 01),
          responsible=None,
          sales=None,
          external_staffing="JCF",
          state="QUALIF",
          deal_id="123456",
          client=Client.objects.get(pk=1),
          salesman=None,
          description="A wonderfull lead that as a so so long description",
          subsidiary=Subsidiary.objects.get(pk=1))

    lead.save()
    return lead


def create_nextcloud_tag_database(connection):
    """Create the test nextcloud database and the 3 tables used for file tagging:
    - oc_filecache: the file index
    - oc_systemtag: the tag definition
    - oc_systemtag_object_mapping: the link between file(s) and tag(s)
    """
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(u"DROP TABLE IF EXISTS `oc_filecache`;")
        create_nextcloud_file_table = u"""
        CREATE TABLE `oc_filecache` (
          `fileid` bigint(20) NOT NULL AUTO_INCREMENT,
          `storage` bigint(20) NOT NULL DEFAULT '0',
          `path` varchar(4000) COLLATE utf8_bin DEFAULT NULL,
          `path_hash` varchar(32) COLLATE utf8_bin NOT NULL DEFAULT '',
          `parent` bigint(20) NOT NULL DEFAULT '0',
          `name` varchar(250) COLLATE utf8_bin DEFAULT NULL,
          `mimetype` bigint(20) NOT NULL DEFAULT '0',
          `mimepart` bigint(20) NOT NULL DEFAULT '0',
          `size` bigint(20) NOT NULL DEFAULT '0',
          `mtime` bigint(20) NOT NULL DEFAULT '0',
          `storage_mtime` bigint(20) NOT NULL DEFAULT '0',
          `encrypted` int(11) NOT NULL DEFAULT '0',
          `unencrypted_size` bigint(20) NOT NULL DEFAULT '0',
          `etag` varchar(40) COLLATE utf8_bin DEFAULT NULL,
          `permissions` int(11) DEFAULT '0',
          `checksum` varchar(255) COLLATE utf8_bin DEFAULT NULL,
          PRIMARY KEY (`fileid`),
          UNIQUE KEY `fs_storage_path_hash` (`storage`,`path_hash`),
          KEY `fs_parent_name_hash` (`parent`,`name`),
          KEY `fs_storage_mimetype` (`storage`,`mimetype`),
          KEY `fs_storage_mimepart` (`storage`,`mimepart`),
          KEY `fs_storage_size` (`storage`,`size`,`fileid`),
          KEY `fs_mtime` (`mtime`)
        ) ENGINE=InnoDB AUTO_INCREMENT=341112 DEFAULT CHARSET=utf8 COLLATE=utf8_bin;
        """
        cursor.execute(create_nextcloud_file_table)

        cursor.execute(u"DROP TABLE IF EXISTS `oc_systemtag`;")
        create_nextcloud_tag_table = u"""
        CREATE TABLE `oc_systemtag` (
          `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
          `name` varchar(64) COLLATE utf8_bin NOT NULL DEFAULT '',
          `visibility` smallint(6) NOT NULL DEFAULT '1',
          `editable` smallint(6) NOT NULL DEFAULT '1',
          PRIMARY KEY (`id`),
          UNIQUE KEY `tag_ident` (`name`,`visibility`,`editable`)
        ) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8 COLLATE=utf8_bin;
        """
        cursor.execute(create_nextcloud_tag_table)

        cursor.execute(u"DROP TABLE IF EXISTS `oc_systemtag_object_mapping`;")
        create_nextcloud_file_tag_table = u"""
        CREATE TABLE `oc_systemtag_object_mapping` (
          `objectid` varchar(64) COLLATE utf8_bin NOT NULL DEFAULT '',
          `objecttype` varchar(64) COLLATE utf8_bin NOT NULL DEFAULT '',
          `systemtagid` bigint(20) unsigned NOT NULL DEFAULT '0',
          UNIQUE KEY `mapping` (`objecttype`,`objectid`,`systemtagid`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_bin;
        """
        cursor.execute(create_nextcloud_file_tag_table)
    finally:
        if cursor:
            cursor.close()
