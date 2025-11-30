from rq import Queue
from redis import Redis
from rq.job import Job

redis = Redis.from_url("redis://localhost:6379/0")
queue = Queue("img_queue", connection=redis)

print("Queued jobs:", queue.count)
job_ids = queue.job_ids
print("Job IDs:", job_ids)

if job_ids:
    job = Job.fetch(job_ids[0], connection=redis)
    print("First job status:", job.get_status())
    print("Meta:", job.meta)
