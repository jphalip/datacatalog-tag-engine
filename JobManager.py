# Copyright 2022 Google, LLC.
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

import uuid, datetime, json, configparser
import constants
from google.cloud import firestore
from google.cloud import tasks_v2


class JobManager:
    """Class for managing jobs for async task create and update requests
    
    project = App Engine project id (e.g. tag-engine-project)
    region = App Engine region (e.g. us-central1)
    queue_name = Cloud Task queue (e.g. tag-engine-queue)
    app_engine_uri = task handler uri set inside the 
                     App Engine project hosting the cloud task queue
    """
    def __init__(self,
                tag_engine_project,
                queue_region,
                queue_name, 
                app_engine_uri):

        self.tag_engine_project = tag_engine_project
        self.queue_region = queue_region
        self.queue_name = queue_name
        self.app_engine_uri = app_engine_uri
        
        self.db = firestore.Client()


##################### API METHODS #################

    def create_job(self, tag_uuid):
        
        print('*** enter create_job ***')
        
        job_uuid = self._create_job_record(tag_uuid)
        resp = self._create_job_task(job_uuid, tag_uuid)
        
        return job_uuid 
        
    
    def update_job_running(self, job_uuid):     

        print('*** update_job_running ***')
        
        job_ref = self.db.collection('jobs').document(job_uuid)
        
        job_ref.set({
            'job_status': 'RUNNING'
        }, merge=True)
        
        print('Set job running.')

    
    def record_num_tasks(self, job_uuid, num_tasks):
        
        print('*** enter record_num_tasks ***')
        
        job_ref = self.db.collection('jobs').document(job_uuid)
        
        job_ref.set({
            'task_count': num_tasks,
        }, merge=True)
        
        print('Set num_tasks.')
        

    def calculate_job_completion(self, job_uuid):
        
        print('*** enter update_job_completed ***')
        
        is_success = False
        is_failed = False
        
        tasks_completed = self._get_tasks_completed(self.db.collection('tasks'), job_uuid, 0)
        tasks_failed = self._get_tasks_failed(self.db.collection('tasks'), job_uuid, 0)
                
        tasks_ran = tasks_completed + tasks_failed
        
        job_ref = self.db.collection('jobs').document(job_uuid)
        job_doc = job_ref.get()

        if job_doc.exists:
            
            job_dict = job_doc.to_dict()
            task_count = job_dict['task_count']
            
            if job_dict['task_count'] > tasks_ran:
                job_ref.set({
                    'tasks_ran': tasks_completed + tasks_failed,
                    'tasks_completed': tasks_completed,
                }, merge=True)
                
                pct_complete = round(tasks_ran / task_count * 100, 2)
            
            if job_dict['task_count'] == tasks_ran:
                
                if job_dict['tasks_failed'] > 0:
                    
                    is_failed = True
                    
                    job_ref.set({
                        'tasks_ran': tasks_completed + tasks_failed,
                        'tasks_completed': tasks_completed,
                        'job_status': 'FAILED',
                        'completion_time': datetime.datetime.utcnow()
                    }, merge=True)
                
                else:
                    
                    is_success = True
                    
                    job_ref.set({
                        'tasks_ran': tasks_completed + tasks_failed,
                        'tasks_completed': tasks_completed,
                        'job_status': 'COMPLETED',
                        'completion_time': datetime.datetime.utcnow()
                    }, merge=True)
                
                pct_complete = 100     

        return is_success, is_failed, pct_complete
                  

    def update_job_failed(self, job_uuid):
        
        print('*** enter update_job_failed ***')
        
        tasks_completed = self._get_tasks_completed(self.db.collection('tasks'), job_uuid, 0)
        tasks_failed = self._get_tasks_failed(self.db.collection('tasks'), job_uuid, 0)
        
        tasks_ran = tasks_completed + tasks_failed
                
        job_ref = self.db.collection('jobs').document(job_uuid)
        job_doc = job_ref.get()

        if job_doc.exists:
            
            job_dict = job_doc.to_dict()
            
            if job_dict['task_count'] > tasks_ran:
                job_ref.set({
                    'tasks_ran': tasks_completed + tasks_failed,
                    'tasks_failed': tasks_failed,
                }, merge=True)
            
            if job_dict['task_count'] == tasks_ran:
                job_ref.set({
                    'tasks_ran': tasks_completed + tasks_failed,
                    'tasks_failed': tasks_failed,
                    'job_status': 'FAILED',
                    'completion_time': datetime.datetime.utcnow()
                }, merge=True)

    
    def get_job_status(self, job_uuid):
        
        job_ref = self.db.collection('jobs').document(job_uuid)
        doc = job_ref.get()
        
        if doc.exists:
            job_dict = doc.to_dict()
            return job_dict
                

################ INTERNAL PROCESSING METHODS #################

    def _create_job_record(self, tag_uuid):
        
        print('*** _create_job_record ***')
        
        job_uuid = uuid.uuid1().hex

        job_ref = self.db.collection('jobs').document(job_uuid)

        job_ref.set({
            'job_uuid': job_uuid,
            'tag_uuid': tag_uuid,
            'job_status':  'PENDING',
            'task_count': 0,
            'tasks_ran': 0,
            'tasks_completed': 0,
            'tasks_failed': 0,
            'creation_time': datetime.datetime.utcnow()
        })
        
        print('Created job record.')
    
        return job_uuid

    
    def _create_job_task(self, job_uuid, tag_uuid):
        
        print('*** enter _create_cloud_task ***')

        client = tasks_v2.CloudTasksClient()
        parent = client.queue_path(self.tag_engine_project, self.queue_region, self.queue_name)
        
        task = {
            'app_engine_http_request': {  
                'http_method':  tasks_v2.HttpMethod.POST,
                'relative_uri': self.app_engine_uri
            }
        }
        
        task['app_engine_http_request']['headers'] = {'Content-type': 'application/json'}
        payload = {'job_uuid': job_uuid, 'tag_uuid': tag_uuid}
        print('payload: ' + str(payload))
        
        payload_utf8 = json.dumps(payload).encode()
        task['app_engine_http_request']['body'] = payload_utf8

        resp = client.create_task(parent=parent, task=task)
        print('resp: ' + str(resp))
        
        return resp
        
    def _get_task_count(job_uuid):
        
        print('*** enter _get_task_count ***')
        
        job_doc = self.db.collection('jobs').document(job_uuid).get()

        if job_doc.exists:
            job_dict = job_doc.to_dict()
            return job_dict['task_count']
        
    def count_collection(coll_ref, count, cursor=None):

        if cursor is not None:
            docs = [snapshot.reference for snapshot
                    in coll_ref.limit(1000).order_by("__name__").start_after(cursor).stream()]
        else:
            docs = [snapshot.reference for snapshot
                    in coll_ref.limit(1000).order_by("__name__").stream()]

        count = count + len(docs)

        if len(docs) == 1000:
            return count_collection(coll_ref, count, docs[999].get())
        else:
            print(count)


    def _get_tasks_completed(self, tasks_ref, job_uuid, count, cursor=None):
        
        if cursor is not None:
            docs = [snapshot.reference for snapshot
                    in tasks_ref.where('job_uuid', '==', job_uuid).where('status', '==', 'COMPLETED').limit(1000).order_by("__name__").start_after(cursor).stream()]
        else:
            docs = [snapshot.reference for snapshot
                    in tasks_ref.where('job_uuid', '==', job_uuid).where('status', '==', 'COMPLETED').limit(1000).order_by("__name__").stream()]
                            
        count = count + len(docs)
        
        if len(docs) == 1000:
            return self._get_tasks_completed(tasks_ref, job_uuid, count, docs[999].get())
        else:
            return count
        

    def _get_tasks_failed(self, tasks_ref, job_uuid, count, cursor=None):
        
        if cursor is not None:
            docs = [snapshot.reference for snapshot
                    in tasks_ref.where('job_uuid', '==', job_uuid).where('status', '==', 'FAILED').limit(1000).order_by("__name__").start_after(cursor).stream()]
        else:
            docs = [snapshot.reference for snapshot
                    in tasks_ref.where('job_uuid', '==', job_uuid).where('status', '==', 'FAILED').limit(1000).order_by("__name__").stream()]
                            
        count = count + len(docs)
        
        if len(docs) == 1000:
            return self._get_tasks_failed(tasks_ref, job_uuid, count, docs[999].get())
        else:
            return count
    
    
if __name__ == '__main__':

    config = configparser.ConfigParser()
    config.read("tagengine.ini")
    
    project = config['DEFAULT']['PROJECT']
    region = config['DEFAULT']['REGION']
    queue_name = config['DEFAULT']['INJECTOR_QUEUE']
    app_engine_uri = '/_split_work'
    jm = JobManager(project, region, queue_name, app_engine_uri)
    
    tag_uuid = '1f1b4720839c11eca541e1ad551502cb'
    jm.create_async_job(tag_uuid)
    
    print('done')



    

    

            
        
