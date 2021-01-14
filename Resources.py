# Copyright 2020 Google, LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from google.cloud import bigquery
import constants

class Resources:
    
    bigquery_resource = "bigquery"
    pubsub_resource = "pubsub"
    gcs_resource = "gs"
    
    def __init__(self, project_id):
        
        self.project_id = project_id
        self.bq_client = bigquery.client.Client(project=project_id)
        
            
    # find BQ resources from uris
    def get_resources(self, included_uris, excluded_uris):
        
        print("enter get_resources")
        print("included_uris: " + included_uris)
        
        included_resources = self.find_resources(included_uris)
        print("included_resources: " + str(included_resources))
        
        if excluded_uris is None or excluded_uris == "" or excluded_uris.isspace():
            return included_resources
        else:
            print("excluded_uris: " + excluded_uris)
            
            excluded_resources = self.find_resources(excluded_uris)
            print("excluded_resources: " + str(excluded_resources))
        
            remaining_resources = included_resources.difference(excluded_resources)
            return remaining_resources

                
    def format_table_resource(self, table_resource):
         # BQ table format: project:dataset.table
         # DC expected resource format: project_id + '/datasets/' + dataset + '/tables/' + short_table
         
        formatted = table_resource.replace(":", "/datasets/").replace(".", "/tables/")
        print("formatted: " + table_resource)
         
        return formatted
         
    def find_resources(self, uris):
       
        # @input uris: comma-separated list of uri representing a BQ resource
        # BQ resources are specified as:  
        # bigquery/project/<project>/dataset/<dataset>/<table>/<column>
        # wildcards are allowed 
        resources = set() 
        
        uri_list = uris.split(",")
        for uri in uri_list:
            
            print("uri: " + uri)
            split_path = uri.strip().split("/")
            resource_type = split_path[0]
            print("resource_type: " + resource_type)
        
            if resource_type != self.bigquery_resource:
                print("Error: bigquery is the only resource type currently supported")
                return None
        
            if split_path[1] != "project":
                print("Error: invalid URI " + path)
                return None
            
            project_id = split_path[2]
               
            dataset = split_path[4]
            dataset_id = project_id + "." + dataset
            
            print("dataset: " + dataset)
            print("dataset_id: " + dataset_id)
            
            dataset = self.bq_client.get_dataset(dataset_id)

            table_expression = split_path[5]
        
            path_length = len(split_path)
            print("path_length: " + str(path_length))
        
            if path_length < 6 or path_length > 7:
                print("Error. Invalid URI " + path)
                return None
        
            if path_length == 6:
                tag_type = constants.BQ_TABLE_TAG
            if path_length == 7:
                tag_type = constants.BQ_COLUMN_TAG
                
            
            if tag_type == constants.BQ_TABLE_TAG:  
            
                if table_expression == "*":
                    print("list all tables in dataset")
                    tables = list(self.bq_client.list_tables(dataset))
                
                    for table in tables:
                        print("full_table_id: " + str(table.full_table_id))
                        formatted_resource = self.format_table_resource(table.full_table_id)
                        resources.add(formatted_resource)
                        
                elif "*" in table_expression:
                    print("table expression contains wildcard")
                    table_substring = table_expression.replace("*", "")
                
                    tables = list(self.bq_client.list_tables(dataset))
                    
                    for table in tables:
                        if table_substring in table.full_table_id:
                            print("full_table_id: " + str(table.full_table_id))
                            formatted_resource = self.format_table_resource(table.full_table_id)
                            resources.add(formatted_resource)
                    
                else:
                    print("table expression == table name")
                    table_id = dataset_id + "." + table_expression
                    
                    try:
                        table = self.bq_client.get_table(table_id)
                        
                        print("full_table_id: " + table.full_table_id)
                        formatted_resource = self.format_table_resource(table.full_table_id)
                        resources.add(formatted_resource)
                        
                    except NotFound:
                        print("NotFound: table " + table_expression + " not found.")
                
            if tag_type == constants.BQ_COLUMN_TAG:
                print("tagging a column")
            
                column_exists = False
                column = split_path[6]
                print("column: " + column)
            
                try:
                    table_id = dataset_id + "." + table_expression
                    print("table_id: " + table_id)
                
                    table = self.bq_client.get_table(table_id)
                    schema = table.schema
                    #print("table schema: " + str(table.schema))
                
                    for schema_field in schema:
                        if schema_field.name == column:
                            column_exists = True
                            break
                    
                    if column_exists == True:
                        print("column exists")
                        table_resource = self.format_table_resource(table.full_table_id)
                        table_column_resource = table_resource + "/column/" + column
                        print("table_column_resource: " + table_column_resource)
                        resources.add(table_column_resource)
                    else:
                        return None
                    
                except NotFound:
                    print("NotFound: table " + table_expression + " not found.")
       
        return resources

if __name__ == '__main__':
    res = Resources(project_id='tag-engine-283315');
    included_uris='bigquery/project/tag-engine-283315/dataset/covid/Employees*, bigquery/project/tag-engine-283315/dataset/covid/Employee_RTO/emp_id, bigquery/project/tag-engine-283315/dataset/views/*'
    excluded_uris=None
    resources = res.get_resources(included_uris, excluded_uris)
    print('resources: ' + str(resources))