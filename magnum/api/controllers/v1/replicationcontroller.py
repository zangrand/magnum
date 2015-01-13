# Copyright 2015 IBM Corp.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import datetime

import pecan
from pecan import rest
import wsme
from wsme import types as wtypes
import wsmeext.pecan as wsme_pecan

from magnum.api.controllers import base
from magnum.api.controllers import link
from magnum.api.controllers.v1 import collection
from magnum.api.controllers.v1 import types
from magnum.api.controllers.v1 import utils as api_utils
from magnum.common import exception
from magnum import objects


class ReplicationControllerPatchType(types.JsonPatchType):

    @staticmethod
    def mandatory_attrs():
        return ['/rc_uuid']


class ReplicationController(base.APIBase):
    """API representation of a ReplicationController.

    This class enforces type checking and value constraints, and converts
    between the internal object model and the API representation of a
    ReplicationController.
    """

    _rc_uuid = None

    def _get_rc_uuid(self):
        return self._rc_uuid

    def _set_rc_uuid(self, value):
        if value and self._rc_uuid != value:
            try:
                rc = objects.ReplicationController.get(pecan.request.context,
                                                       value)
                self._rc_uuid = rc.uuid
                # NOTE(jay-lau-513): Create the rc_id attribute on-the-fly
                #                    to satisfy the api -> rpc object
                #                    conversion.
                self.rc_id = rc.id
            except exception.ReplicationControllerNotFound as e:
                # Change error code because 404 (NotFound) is inappropriate
                # response for a POST request to create a rc
                e.code = 400  # BadRequest
                raise e
        elif value == wtypes.Unset:
            self._rc_uuid = wtypes.Unset

    uuid = types.uuid
    """Unique UUID for this ReplicationController"""

    name = wtypes.text
    """Name of this ReplicationController"""

    images = [wtypes.text]
    """A list of images used by containers in this ReplicationController."""

    bay_uuid = types.uuid
    """Unique UUID of the bay the ReplicationController runs on"""

    selector = {wtypes.text: wtypes.text}
    """Selector of this ReplicationController"""

    replicas = wtypes.IntegerType()
    """Replicas of this ReplicationController"""

    rc_definition_url = wtypes.text
    """URL for ReplicationController file to create the RC"""

    rc_data = wtypes.text
    """Data for service to create the ReplicationController"""

    links = wsme.wsattr([link.Link], readonly=True)
    """A list containing a self link and associated rc links"""

    def __init__(self, **kwargs):
        super(ReplicationController, self).__init__()

        self.fields = []
        fields = list(objects.ReplicationController.fields)
        # NOTE(jay-lau-513): rc_uuid is not part of
        #                    objects.ReplicationController.fields
        #                    because it's an API-only attribute
        fields.append('rc_uuid')
        for field in fields:
            # Skip fields we do not expose.
            if not hasattr(self, field):
                continue
            self.fields.append(field)
            setattr(self, field, kwargs.get(field, wtypes.Unset))

        # NOTE(jay-lau-513): rc_id is an attribute created on-the-fly
        # by _set_rc_uuid(), it needs to be present in the fields so
        # that as_dict() will contain rc_id field when converting it
        # before saving it in the database.
        self.fields.append('rc_id')
        setattr(self, 'rc_uuid', kwargs.get('rc_id', wtypes.Unset))

    @staticmethod
    def _convert_with_links(rc, url, expand=True):
        if not expand:
            rc.unset_fields_except(['uuid', 'name', 'images', 'bay_uuid',
                                    'selector', 'replicas'])

        # never expose the rc_id attribute
        rc.rc_id = wtypes.Unset

        rc.links = [link.Link.make_link('self', url,
                                         'rcs', rc.uuid),
                     link.Link.make_link('bookmark', url,
                                         'rcs', rc.uuid,
                                         bookmark=True)
                     ]
        return rc

    @classmethod
    def convert_with_links(cls, rpc_rc, expand=True):
        rc = ReplicationController(**rpc_rc.as_dict())
        return cls._convert_with_links(rc, pecan.request.host_url, expand)

    @classmethod
    def sample(cls, expand=True):
        sample = cls(uuid='f978db47-9a37-4e9f-8572-804a10abc0aa',
                     name='MyReplicationController',
                     images=['MyImage'],
                     bay_uuid='f978db47-9a37-4e9f-8572-804a10abc0ab',
                     selector={'name': 'foo'},
                     replicas=2,
                     created_at=datetime.datetime.utcnow(),
                     updated_at=datetime.datetime.utcnow())
        # NOTE(jay-lau-513): rc_uuid getter() method look at the
        # _rc_uuid variable
        sample._rc_uuid = '87504bd9-ca50-40fd-b14e-bcb23ed42b27'
        return cls._convert_with_links(sample, 'http://localhost:9511', expand)


class ReplicationControllerCollection(collection.Collection):
    """API representation of a collection of ReplicationControllers."""

    rcs = [ReplicationController]
    """A list containing ReplicationController objects"""

    def __init__(self, **kwargs):
        self._type = 'rcs'

    @staticmethod
    def convert_with_links(rpc_rcs, limit, url=None, expand=False, **kwargs):
        collection = ReplicationControllerCollection()
        collection.rcs = [ReplicationController.convert_with_links(p, expand)
                           for p in rpc_rcs]
        collection.next = collection.get_next(limit, url=url, **kwargs)
        return collection

    @classmethod
    def sample(cls):
        sample = cls()
        sample.rcs = [ReplicationController.sample(expand=False)]
        return sample


class ReplicationControllersController(rest.RestController):
    """REST controller for ReplicationControllers."""

    def __init__(self):
        super(ReplicationControllersController, self).__init__()

    from_rcs = False
    """A flag to indicate if the requests to this controller are coming
    from the top-level resource ReplicationControllers."""

    _custom_actions = {
        'detail': ['GET'],
    }

    def _get_rcs_collection(self, marker, limit,
                             sort_key, sort_dir, expand=False,
                             resource_url=None):

        limit = api_utils.validate_limit(limit)
        sort_dir = api_utils.validate_sort_dir(sort_dir)

        marker_obj = None
        if marker:
            marker_obj = objects.ReplicationController.get_by_uuid(
                                                 pecan.request.context,
                                                 marker)

        rcs = pecan.request.rpcapi.rc_list(pecan.request.context, limit,
                                         marker_obj, sort_key=sort_key,
                                         sort_dir=sort_dir)

        return ReplicationControllerCollection.convert_with_links(rcs, limit,
                                                url=resource_url,
                                                expand=expand,
                                                sort_key=sort_key,
                                                sort_dir=sort_dir)

    @wsme_pecan.wsexpose(ReplicationControllerCollection, types.uuid,
                         types.uuid, int, wtypes.text, wtypes.text)
    def get_all(self, rc_uuid=None, marker=None, limit=None,
                sort_key='id', sort_dir='asc'):
        """Retrieve a list of ReplicationControllers.

        :param marker: pagination marker for large data sets.
        :param limit: maximum number of resources to return in a single result.
        :param sort_key: column to sort results by. Default: id.
        :param sort_dir: direction to sort. "asc" or "desc". Default: asc.
        """
        return self._get_rcs_collection(marker, limit, sort_key,
                                        sort_dir)

    @wsme_pecan.wsexpose(ReplicationControllerCollection, types.uuid,
                         types.uuid, int, wtypes.text, wtypes.text)
    def detail(self, rc_uuid=None, marker=None, limit=None,
               sort_key='id', sort_dir='asc'):
        """Retrieve a list of ReplicationControllers with detail.

        :param rc_uuid: UUID of a ReplicationController, to get only
                         ReplicationControllers for the ReplicationController.
        :param marker: pagination marker for large data sets.
        :param limit: maximum number of resources to return in a single result.
        :param sort_key: column to sort results by. Default: id.
        :param sort_dir: direction to sort. "asc" or "desc". Default: asc.
        """
        # NOTE(jay-lau-513): /detail should only work agaist collections
        parent = pecan.request.path.split('/')[:-1][-1]
        if parent != "rcs":
            raise exception.HTTPNotFound

        expand = True
        resource_url = '/'.join(['rcs', 'detail'])
        return self._get_rcs_collection(marker, limit,
                                         sort_key, sort_dir, expand,
                                         resource_url)

    @wsme_pecan.wsexpose(ReplicationController, types.uuid)
    def get_one(self, rc_uuid):
        """Retrieve information about the given ReplicationController.

        :param rc_uuid: UUID of a ReplicationController.
        """
        if self.from_rcs:
            raise exception.OperationNotPermitted

        rpc_rc = objects.ReplicationController.get_by_uuid(
                                      pecan.request.context, rc_uuid)
        return ReplicationController.convert_with_links(rpc_rc)

    @wsme_pecan.wsexpose(ReplicationController, body=ReplicationController,
                         status_code=201)
    def post(self, rc):
        """Create a new ReplicationController.

        :param rc: a ReplicationController within the request body.
        """
        if self.from_rcs:
            raise exception.OperationNotPermitted

        rc_obj = objects.ReplicationController(pecan.request.context,
                              **rc.as_dict())
        new_rc = pecan.request.rpcapi.rc_create(rc_obj)
        # Set the HTTP Location Header
        pecan.response.location = link.build_url('rcs', new_rc.uuid)
        return ReplicationController.convert_with_links(new_rc)

    @wsme.validate(types.uuid, [ReplicationControllerPatchType])
    @wsme_pecan.wsexpose(ReplicationController, types.uuid,
                         body=[ReplicationControllerPatchType])
    def patch(self, rc_uuid, patch):
        """Update an existing rc.

        :param rc_uuid: UUID of a ReplicationController.
        :param patch: a json PATCH document to apply to this rc.
        """
        if self.from_rcs:
            raise exception.OperationNotPermitted

        rpc_rc = objects.ReplicationController.get_by_uuid(
                                    pecan.request.context, rc_uuid)
        try:
            rc_dict = rpc_rc.as_dict()
            # NOTE(jay-lau-513):
            # 1) Remove rc_id because it's an internal value and
            #    not present in the API object
            # 2) Add rc_uuid
            rc_dict['rc_uuid'] = rc_dict.pop('rc_id', None)
            rc = ReplicationController(**api_utils.apply_jsonpatch(rc_dict,
                                                                   patch))
        except api_utils.JSONPATCH_EXCEPTIONS as e:
            raise exception.PatchError(patch=patch, reason=e)

        # Update only the fields that have changed
        for field in objects.ReplicationController.fields:
            # ignore rc_definition_url as it was used for create rc
            if field == 'rc_definition_url':
                continue
            # ignore rc_data as it was used for create rc
            if field == 'rc_data':
                continue
            try:
                patch_val = getattr(rc, field)
            except AttributeError:
                # Ignore fields that aren't exposed in the API
                continue
            if patch_val == wtypes.Unset:
                patch_val = None
            if rpc_rc[field] != patch_val:
                rpc_rc[field] = patch_val

        rpc_rc.save()
        return ReplicationController.convert_with_links(rpc_rc)

    @wsme_pecan.wsexpose(None, types.uuid, status_code=204)
    def delete(self, rc_uuid):
        """Delete a ReplicationController.

        :param rc_uuid: UUID of a ReplicationController.
        """
        if self.from_rcs:
            raise exception.OperationNotPermitted

        rpc_rc = objects.ReplicationController.get_by_uuid(
                                    pecan.request.context, rc_uuid)
        pecan.request.rpcapi.rc_delete(rpc_rc)
