import json
import logging
from typing import List

import custom_connector_sdk.lambda_handler.requests as requests
import custom_connector_sdk.lambda_handler.responses as responses
import custom_connector_sdk.connector.context as context
import custom_connector_sdk.connector.fields as fields
import custom_connector_example.handlers.validation as validation
import custom_connector_example.handlers.salesforce as salesforce
from custom_connector_sdk.lambda_handler.handlers import MetadataHandler

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

SALESFORCE_SOBJECTS_URL_FORMAT = '{}services/data/{}/sobjects'
SALESFORCE_SOBJECT_DESCRIBE_URL_FORMAT = '{}services/data/{}/sobjects/{}/describe'
# https://org1deca345.crm7.dynamics.com/api/data/v9.2/EntityDefinitions?$select=LogicalName&$filter=CanCreateAttributes/Value%20eq%20true
# https://dev.{servername}/api/discovery/v9.1/Instances(UniqueName='myorg')  
#  request_uri = url_format.format(instance_url, api_version, request_path)
# [Organization URI]/api/data/v9.2/EntityDefinitions
# /api/data/v9.2/EntityDefinitions(LogicalName='account') 
D365_OBJECT_URL_FORMAT = '{}api/data/{}/EntityDefinitions?$select=LogicalName&$filter=CanCreateAttributes/Value%20eq%20true' 
D365_OBJECT_DESCRIBE_URL_FORMAT =  "{}api/data/{}/EntityDefinitions(LogicalName='{}')?$select=LogicalName,SchemaName,DisplayName,LogicalCollectionName,EntitySetName,PrimaryIdAttribute&$expand=Attributes($select=LogicalName,AttributeType,DisplayName,IsPrimaryId,IsPrimaryName)"
# https://org1deca345.crm7.dynamics.com/api/data/v9.2/EntityDefinitions(LogicalName='account')/Attributes
# Salesforce response keys
SOBJECTS_KEY = 'sobjects'
OBJECT_DESCRIBE_KEY = 'objectDescribe'
CHILD_RELATIONSHIPS_KEY = 'childRelationships'
HAS_SUBTYPES_KEY = 'hasSubtypes'
NAME_KEY = 'name'
FIELDS_KEY = 'Attributes'
TYPE_KEY = 'type'
LABEL_KEY = 'LogicalName'
# 'LogicalCollectionName'
FILTERABLE_KEY = 'filterable'
EXTERNAL_ID_KEY = 'externalId'
ID_LOOKUP_KEY = 'idLookup'
CREATEABLE_KEY = 'createable'
UPDATEABLE_KEY = 'updateable'
NILLABLE_KEY = 'nillable'
DEFAULTED_ON_CREATE_KEY = 'defaultedOnCreate'
DEFAULT_VALUE_KEY = 'defaultValue'
UNIQUE_KEY = 'unique'

ACCOUNT_ENTITY = context.Entity(
    entity_identifier="2a4901bf-2241-db11-898a-0007e9e17ebd",
    label="Account",
    has_nested_entities=False,
    description="Account description",
    is_writable=False
)
def parse_entities(json_string: str) -> List[context.Entity]:
    """Parse JSON response from Salesforce query into a list of Entities."""
    parent_object = json.loads(json_string)
    entity_list = []
    for entity in parent_object['value']:
        entity_list.append(build_entity(entity))
    #     # print entity['restaurant']['name']
    #     entity_list
    # if parent_object.get(SOBJECTS_KEY):
    #     sobjects = parent_object.get(SOBJECTS_KEY)
    #     for sobject in sobjects:
    #         entity_list.append(build_entity(sobject))
    # elif parent_object.get(OBJECT_DESCRIBE_KEY):
    #     entity_list.append(build_entity(parent_object.get(OBJECT_DESCRIBE_KEY)))

    return entity_list

def build_entity(field: dict) -> context.Entity:
    """Build Entity from Salesforce field."""
    logical_name = field.get(LABEL_KEY)
    # metadata_id = field.get('MetadataId')
    return context.Entity(entity_identifier=logical_name,
                          label=logical_name,
                          has_nested_entities=False,
                          description=logical_name,
                          is_writable=False)

def parse_entity_definition(json_string: str) -> context.EntityDefinition:
    """Parse JSON response from Salesforce query into an entity definition."""
    parent_object = json.loads(json_string)

    field_definitions = []
    entity = build_entity(parent_object)

    if FIELDS_KEY in parent_object:
        field_list = parent_object.get(FIELDS_KEY)
        for field in field_list:
            field_definitions.append(build_field_definition(field))
    return context.EntityDefinition(entity=entity, fields=field_definitions)

def build_field_definition(field: dict) -> context.FieldDefinition:
    """Build FieldDefinition from Salesforce field.`"""
    data_type_label = salesforce.get_string_value(field, 'AttributeType')
    data_type = convert_data_type(data_type_label)
   


    return context.FieldDefinition(field_name=field.get(LABEL_KEY),
                                data_type=data_type,
                                data_type_label=data_type_label,
                                label=field.get(LABEL_KEY),
                                description=field.get(LABEL_KEY),
                                default_value="1970-01-01 00:00:00",
                                is_primary_key=field.get('IsPrimaryId'),
                                read_properties=fields.ReadOperationProperty(
                                is_queryable=True,
                                is_retrievable=True,
                                is_nullable=False,
                                is_timestamp_field_for_incremental_queries=False,
                                 ),
                                write_properties=None)

def convert_data_type(data_type_name: str):
    data_type_map = {
        'int': fields.FieldDataType.Integer,
        'double': fields.FieldDataType.Double,
        'long': fields.FieldDataType.Long,
        'id': fields.FieldDataType.String,
        'string': fields.FieldDataType.String,
        'textarea': fields.FieldDataType.String,
        'date': fields.FieldDataType.Date,
        'datetime': fields.FieldDataType.DateTime,
        'time': fields.FieldDataType.DateTime,
        'boolean': fields.FieldDataType.Boolean
    }
    try:
        return data_type_map[data_type_name]
    except KeyError:
        return fields.FieldDataType.Struct

class SalesforceMetadataHandler(MetadataHandler):
    """Salesforce Metadata handler."""
    def list_entities(self, request: requests.ListEntitiesRequest) -> responses.ListEntitiesResponse:
        error_details = validation.validate_request_connector_context(request)
        if error_details:
            LOGGER.error('ListEntities request failed with ' + str(error_details))
            return responses.ListEntitiesResponse(is_success=False, error_details=error_details)
        if request.entities_path:
            request_uri = salesforce.build_salesforce_request_uri(connector_context=request.connector_context,
                                                                  url_format=D365_OBJECT_URL_FORMAT,
                                                                  request_path=request.entities_path)
        else:
            request_uri = salesforce.build_salesforce_request_uri(connector_context=request.connector_context,
                                                                  url_format=D365_OBJECT_URL_FORMAT,
                                                                  request_path='')

        salesforce_response = salesforce.get_salesforce_client(request.connector_context).rest_get(request_uri)
        error_details = salesforce.check_for_errors_in_salesforce_response(salesforce_response)
        if error_details:
            return responses.ListEntitiesResponse(is_success=False, error_details=error_details)
        return responses.ListEntitiesResponse(is_success=True, entities=parse_entities(salesforce_response.response))

    def describe_entity(self, request: requests.DescribeEntityRequest) -> responses.DescribeEntityResponse:
        error_details = validation.validate_request_connector_context(request)
        if error_details:
            LOGGER.error('DescribeEntity request failed with ' + str(error_details))
            return responses.DescribeEntityResponse(is_success=False, error_details=error_details)


        LOGGER.error(f'test -> request.entity_identifier === {request.entity_identifier}')
        request_uri = salesforce.build_salesforce_request_uri(connector_context=request.connector_context,
                                                              url_format=D365_OBJECT_DESCRIBE_URL_FORMAT,
                                                              request_path=request.entity_identifier)
        # LOGGER.error(f'test ->request_uri === {request_uri}')
        salesforce_response = salesforce.get_salesforce_client(request.connector_context).rest_get(request_uri)
        error_details = salesforce.check_for_errors_in_salesforce_response(salesforce_response)

        LOGGER.error(f'salesforce_response.response =>> {salesforce_response.response}')
        if error_details:
            return responses.DescribeEntityResponse(is_success=False, error_details=error_details)
        

        parsed_entity_definition = parse_entity_definition(salesforce_response.response)

        LOGGER.error(f'test parsed entity_definition =>> {parsed_entity_definition}')
        return responses.DescribeEntityResponse(is_success=True,
                                                entity_definition=parsed_entity_definition)
