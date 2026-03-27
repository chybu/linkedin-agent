import linkedin_tool.schema as schema
import linkedin_tool.client as client

time_range = schema.TimePostedRange.PAST_24H
work_place = schema.WorkplaceType.ON_SITE
experience = schema.ExperienceLevel.INTERN
job_type = schema.JobType.INTERNSHIP
sort = schema.SortBy.MOST_RELEVANT

keyword = "teacher"
geoid = schema.GeoId.CALIFORNIA

request = schema.JobSearchRequest(
    geo_id=geoid,
    keywords=keyword,
    sort_by=sort
)

print(client.LinkedinClient._get_job_search_url(request))
