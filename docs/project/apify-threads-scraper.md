
範例
#####

from apify_client import ApifyClient

# Initialize the ApifyClient with your Apify API token
# Replace '<YOUR_API_TOKEN>' with your token.
client = ApifyClient("<YOUR_API_TOKEN>")

# Prepare the Actor input
run_input = {
    "urls": ["@zuck"],
    "postsPerSource": 25,
}

# Run the Actor and wait for it to finish
run = client.actor("curious_coder/threads-scraper").call(run_input=run_input)

# Fetch and print Actor results from the run's dataset (if there are any)
print("💾 Check your data here: https://console.apify.com/storage/datasets/" + run["defaultDatasetId"])
for item in client.dataset(run["defaultDatasetId"]).iterate_items():
    print(item)

# 📚 Want to learn more 📖? Go to → https://docs.apify.com/api/client/python/docs/quick-start

##########

The Apify client for Python is the official library to access the Apify REST API from your Python applications. It provides useful features like automatic retries and convenience functions that improve the experience of using the Apify API. All requests and responses (including errors) are encoded in JSON format with UTF-8 encoding. The client provides both synchronous and asynchronous interfaces.

from apify_client import ApifyClientAsync

# You can find your API token at https://console.apify.com/settings/integrations.
TOKEN = 'MY-APIFY-TOKEN'


async def main() -> None:
    apify_client = ApifyClientAsync(TOKEN)

    # Start an Actor and wait for it to finish.
    actor_client = apify_client.actor('john-doe/my-cool-actor')
    call_result = await actor_client.call()

    if call_result is None:
        print('Actor run failed.')
        return

    # Fetch results from the Actor run's default dataset.
    dataset_client = apify_client.dataset(call_result['defaultDatasetId'])
    list_items_result = await dataset_client.list_items()
    print(f'Dataset: {list_items_result}')

######

The Apify API (version 2) provides programmatic access to the [Apify platform](https://docs.apify.com/). The API is organized around [RESTful](https://en.wikipedia.org/wiki/Representational_state_transfer) HTTP endpoints.

You can download the complete OpenAPI schema of Apify API in the [YAML](http://docs.apify.com/api/openapi.yaml) or [JSON](http://docs.apify.com/api/openapi.json) formats. The source code is also available on [GitHub](https://github.com/apify/apify-docs/tree/master/apify-api/openapi).

All requests and responses (including errors) are encoded in [JSON](http://www.json.org/) format with UTF-8 encoding, with a few exceptions that are explicitly described in the reference.

To access the API using [Node.js](https://nodejs.org/en/), we recommend the [`apify-client`](https://docs.apify.com/api/client/js) [NPM package](https://www.npmjs.com/package/apify-client).

To access the API using [Python](https://www.python.org/), we recommend the [`apify-client`](https://docs.apify.com/api/client/python) [PyPI package](https://pypi.org/project/apify-client/). The clients' functions correspond to the API endpoints and have the same parameters. This simplifies development of apps that depend on the Apify platform.

**Note:** All requests with JSON payloads need to specify the `Content-Type: application/json` HTTP header! All API endpoints support the `method` query parameter that can override the HTTP method. For example, if you want to call a POST endpoint using a GET request, simply add the query parameter `method=POST` to the URL and send the GET request. This feature is especially useful if you want to call Apify API endpoints from services that can only send GET requests.

## Authentication[](https://docs.apify.com/api/v2#authentication "Direct link to Authentication")

You can find your API token on the [Integrations](https://console.apify.com/account#/integrations) page in the Apify Console.

To use your token in a request, either:

-   Add the token to your request's `Authorization` header as `Bearer <token>`. E.g., `Authorization: Bearer xxxxxxx`. [More info](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Authorization). (Recommended).
-   Add it as the `token` parameter to your request URL. (Less secure).

Using your token in the request header is more secure than using it as a URL parameter because URLs are often stored in browser history and server logs. This creates a chance for someone unauthorized to access your API token.

**Do not share your API token or password with untrusted parties.**

For more information, see our [integrations](https://docs.apify.com/platform/integrations) documentation.

## Basic usage[](https://docs.apify.com/api/v2#basic-usage "Direct link to Basic usage")

To run an Actor, send a POST request to the [Run Actor](https://docs.apify.com/api/v2#/reference/actors/run-collection/run-actor) endpoint using either the Actor ID code (e.g. `vKg4IjxZbEYTYeW8T`) or its name (e.g. `janedoe~my-actor`):

`https://api.apify.com/v2/acts/[actor_id]/runs`

If the Actor is not runnable anonymously, you will receive a 401 or 403 [response code](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status). This means you need to add your [secret API token](https://console.apify.com/account#/integrations) to the request's `Authorization` header ([recommended](https://docs.apify.com/api/v2#/introduction/authentication)) or as a URL query parameter `?token=[your_token]` (less secure).

Optionally, you can include the query parameters described in the [Run Actor](https://docs.apify.com/api/v2#/reference/actors/run-collection/run-actor) section to customize your run.

If you're using Node.js, the best way to run an Actor is using the `Apify.call()` method from the [Apify SDK](https://sdk.apify.com/docs/api/apify#apifycallactid-input-options). It runs the Actor using the account you are currently logged into (determined by the [secret API token](https://console.apify.com/account#/integrations)). The result is an [Actor run object](https://sdk.apify.com/docs/typedefs/actor-run) and its output (if any).

A typical workflow is as follows:

1.  Run an Actor or task using the [Run Actor](https://docs.apify.com/api/v2#/reference/actors/run-collection/run-actor) or [Run task](https://docs.apify.com/api/v2#/reference/actor-tasks/run-collection/run-task) API endpoints.
2.  Monitor the Actor run by periodically polling its progress using the [Get run](https://docs.apify.com/api/v2#/reference/actor-runs/run-object-and-its-storages/get-run) API endpoint.
3.  Fetch the results from the [Get items](https://docs.apify.com/api/v2#/reference/datasets/item-collection/get-items) API endpoint using the `defaultDatasetId`, which you receive in the Run request response. Additional data may be stored in a key-value store. You can fetch them from the [Get record](https://docs.apify.com/api/v2#/reference/key-value-stores/record/get-record) API endpoint using the `defaultKeyValueStoreId` and the store's `key`.

**Note**: Instead of periodic polling, you can also run your [Actor](https://docs.apify.com/api/v2#/reference/actors/run-actor-synchronously) or [task](https://docs.apify.com/api/v2#/reference/actor-tasks/runs-collection/run-task-synchronously) synchronously. This will ensure that the request waits for 300 seconds (5 minutes) for the run to finish and returns its output. If the run takes longer, the request will time out and throw an error.

## Response structure[](https://docs.apify.com/api/v2#response-structure "Direct link to Response structure")

Most API endpoints return a JSON object with the `data` property:

However, there are a few explicitly described exceptions, such as Dataset [Get items](https://docs.apify.com/api/v2#/reference/datasets/item-collection/get-items) or Key-value store [Get record](https://docs.apify.com/api/v2#/reference/key-value-stores/record/get-record) API endpoints, which return data in other formats. In case of an error, the response has the HTTP status code in the range of 4xx or 5xx and the `data` property is replaced with `error`. For example:

```json
{    "error": {        "type": "record-not-found",        "message": "Store was not found."    }}
```

See [Errors](https://docs.apify.com/api/v2#/introduction/errors) for more details.

All API endpoints that return a list of records (e.g. [Get list of Actors](https://docs.apify.com/api/v2#/reference/actors/actor-collection/get-list-of-actors)) enforce pagination in order to limit the size of their responses.

Most of these API endpoints are paginated using the `offset` and `limit` query parameters. The only exception is [Get list of keys](https://docs.apify.com/api/v2#/reference/key-value-stores/key-collection/get-list-of-keys), which is paginated using the `exclusiveStartKey` query parameter.

**IMPORTANT**: Each API endpoint that supports pagination enforces a certain maximum value for the `limit` parameter, in order to reduce the load on Apify servers. The maximum limit could change in future so you should never rely on a specific value and check the responses of these API endpoints.

### Using offset[](https://docs.apify.com/api/v2#using-offset "Direct link to Using offset")

Most API endpoints that return a list of records enable pagination using the following query parameters:

| `limit`  |                                                                                                                                                 Limits the response to contain a specific maximum number of items, e.g. `limit=20`.                                                                                                                                                 |
|--------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `offset` |                                                                                                                                                     Skips a number of items from the beginning of the list, e.g. `offset=100`.                                                                                                                                                      |
|  `desc`  | By default, items are sorted in the order in which they were created or added to the list. This feature is useful when fetching all the items, because it ensures that items created after the client started the pagination will not be skipped. If you specify the `desc=1` parameter, the items will be returned in the reverse order, i.e. from the newest to the oldest items. |

The response of these API endpoints is always a JSON object with the following structure:

```csharp
{    "data": {        "total": 2560,        "offset": 250,        "limit": 1000,        "count": 1000,        "desc": false,        "items": [            { 1st object },            { 2nd object },            ...            { 1000th object }        ]    }}
```

The following table describes the meaning of the response properties:

| Property |                                                                                                      Description                                                                                                      |
|----------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|  `total`   |                                                                                   The total number of items available in the list.                                                                                    |
|  `offset`  |                                        The number of items that were skipped at the start. This is equal to the `offset` query parameter if it was provided, otherwise it is `0`.                                         |
|  `limit`   | The maximum number of items that can be returned in the HTTP response. It equals to the `limit` query parameter if it was provided or the maximum limit enforced for the particular API endpoint, whichever is smaller. |
|  `count`   |                                                                               The actual number of items returned in the HTTP response.                                                                               |
|   `desc`   |                                                                         `true` if data were requested in descending order and `false` otherwise.                                                                          |
|  `items`   |                                                                                             An array of requested items.                                                                                              |

### Using key[](https://docs.apify.com/api/v2#using-key "Direct link to Using key")

The records in the [key-value store](https://docs.apify.com/platform/storage/key-value-store) are not ordered based on numerical indexes, but rather by their keys in the UTF-8 binary order. Therefore the [Get list of keys](https://docs.apify.com/api/v2#/reference/key-value-stores/key-collection/get-list-of-keys) API endpoint only supports pagination using the following query parameters:

|       `limit`       |           Limits the response to contain a specific maximum number items, e.g. `limit=20`.            |
|-------------------|-----------------------------------------------------------------------------------------------------|
| `exclusiveStartKey` | Skips all records with keys up to the given key including the given key, in the UTF-8 binary order. |

The response of the API endpoint is always a JSON object with following structure:

```csharp
{    "data": {        "limit": 1000,        "isTruncated": true,        "exclusiveStartKey": "my-key",        "nextExclusiveStartKey": "some-other-key",        "items": [            { 1st object },            { 2nd object },            ...            { 1000th object }        ]    }}
```

The following table describes the meaning of the response properties:

|       Property        |                                                                                                    Description                                                                                                    |
|-----------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|         `limit`         | The maximum number of items that can be returned in the HTTP response. It equals to the `limit` query parameter if it was provided or the maximum limit enforced for the particular endpoint, whichever is smaller. |
|      `isTruncated`      |                                                                         `true` if there are more items left to be queried. Otherwise `false`.                                                                         |
|   `exclusiveStartKey`   |                                                                      The last key that was skipped at the start. Is `null` for the first page.                                                                      |
| `nextExclusiveStartKey` |                                                                  The value for the `exclusiveStartKey` parameter to query the next page of items.                                                                   |

## Errors[](https://docs.apify.com/api/v2#errors "Direct link to Errors")

The Apify API uses common HTTP status codes: `2xx` range for success, `4xx` range for errors caused by the caller (invalid requests) and `5xx` range for server errors (these are rare). Each error response contains a JSON object defining the `error` property, which is an object with the `type` and `message` properties that contain the error code and a human-readable error description, respectively.

For example:

```json
{    "error": {        "type": "record-not-found",        "message": "Store was not found."    }}
```

Here is the table of the most common errors that can occur for many API endpoints:

| status |        type         |                                        message                                         |
|--------|---------------------|----------------------------------------------------------------------------------------|
|  `400`   |   `invalid-request`   |                            POST data must be a JSON object                             |
|  `400`   |    `invalid-value`    |                       Invalid value provided: Comments required                        |
|  `400`   | `invalid-record-key`  |                         Record key contains invalid character                          |
|  `401`   | `token-not-provided`  |                         Authentication token was not provided                          |
|  `404`   |  `record-not-found`   |                                  Store was not found                                   |
|  `429`   | `rate-limit-exceeded` |               You have exceeded the rate limit of 30 requests per second               |
|  `405`   | `method-not-allowed`  | This API endpoint can only be accessed using the following HTTP methods: OPTIONS, POST |

## Rate limiting[](https://docs.apify.com/api/v2#rate-limiting "Direct link to Rate limiting")

All API endpoints limit the rate of requests in order to prevent overloading of Apify servers by misbehaving clients.

There are two kinds of rate limits - a global rate limit and a per-resource rate limit.

### Global rate limit[](https://docs.apify.com/api/v2#global-rate-limit "Direct link to Global rate limit")

The global rate limit is set to _250 000 requests per minute_. For [authenticated](https://docs.apify.com/api/v2#/introduction/authentication) requests, it is counted per user, and for unauthenticated requests, it is counted per IP address.

### Per-resource rate limit[](https://docs.apify.com/api/v2#per-resource-rate-limit "Direct link to Per-resource rate limit")

The default per-resource rate limit is _30 requests per second per resource_, which in this context means a single Actor, a single Actor run, a single dataset, single key-value store etc. The default rate limit is applied to every API endpoint except a few select ones, which have higher rate limits. Each API endpoint returns its rate limit in `X-RateLimit-Limit` header.

These endpoints have a rate limit of _100 requests per second per resource_:

-   CRUD ([get](https://docs.apify.com/api/v2#/reference/key-value-stores/record/get-record), [put](https://docs.apify.com/api/v2#/reference/key-value-stores/record/put-record), [delete](https://docs.apify.com/api/v2#/reference/key-value-stores/record/delete-record)) operations on key-value store records

These endpoints have a rate limit of _200 requests per second per resource_:

-   [Run Actor](https://docs.apify.com/api/v2#/reference/actors/run-collection/run-actor)
-   [Run Actor task asynchronously](https://docs.apify.com/api/v2#/reference/actor-tasks/runs-collection/run-task-asynchronously)
-   [Run Actor task synchronously](https://docs.apify.com/api/v2#/reference/actor-tasks/runs-collection/run-task-synchronously)
-   [Metamorph Actor run](https://docs.apify.com/api/v2#/reference/actors/metamorph-run/metamorph-run)
-   [Push items](https://docs.apify.com/api/v2#/reference/datasets/item-collection/put-items) to dataset
-   CRUD ([add](https://docs.apify.com/api/v2#/reference/request-queues/request-collection/add-request), [get](https://docs.apify.com/api/v2#/reference/request-queues/request-collection/get-request), [update](https://docs.apify.com/api/v2#/reference/request-queues/request-collection/update-request), [delete](https://docs.apify.com/api/v2#/reference/request-queues/request-collection/delete-request)) operations on requests in request queues

### Rate limit exceeded errors[](https://docs.apify.com/api/v2#rate-limit-exceeded-errors "Direct link to Rate limit exceeded errors")

If the client is sending too many requests, the API endpoints respond with the HTTP status code `429 Too Many Requests` and the following body:

```json
{    "error": {        "type": "rate-limit-exceeded",        "message": "You have exceeded the rate limit of ... requests per second"    }}
```

### Retrying rate-limited requests with exponential backoff[](https://docs.apify.com/api/v2#retrying-rate-limited-requests-with-exponential-backoff "Direct link to Retrying rate-limited requests with exponential backoff")

If the client receives the rate limit error, it should wait a certain period of time and then retry the request. If the error happens again, the client should double the wait period and retry the request, and so on. This algorithm is known as _exponential backoff_ and it can be described using the following pseudo-code:

1.  Define a variable `DELAY=500`
2.  Send the HTTP request to the API endpoint
3.  If the response has status code not equal to `429` then you are done. Otherwise:
    -   Wait for a period of time chosen randomly from the interval `DELAY` to `2*DELAY` milliseconds
    -   Double the future wait period by setting `DELAY = 2*DELAY`
    -   Continue with step 2

If all requests sent by the client implement the above steps, the client will automatically use the maximum available bandwidth for its requests.

Note that the Apify API clients [for JavaScript](https://docs.apify.com/api/client/js) and [for Python](https://docs.apify.com/api/client/python) use the exponential backoff algorithm transparently, so that you do not need to worry about it.

## Referring to resources[](https://docs.apify.com/api/v2#referring-to-resources "Direct link to Referring to resources")

There are three main ways to refer to a resource you're accessing via API.

-   the resource ID (e.g. `iKkPcIgVvwmztduf8`)
-   `username~resourcename` - when using this access method, you will need to use your API token, and access will only work if you have the correct permissions.
-   `~resourcename` - for this, you need to use an API token, and the `resourcename` refers to a resource in the API token owner's account.

## Authentication[](https://docs.apify.com/api/v2#authentication "Direct link to Authentication")

-   HTTP: Bearer Auth
-   HTTP: Bearer Auth
-   HTTP: Bearer Auth
-   HTTP: Bearer Auth
-   API Key: apiKey
-   API Key: apiKeyActorBuilds
-   API Key: apiKeyStoreId
-   API Key: apiKeyQueueId

API authentication token.

|   Security Scheme Type:    |  http  |
|----------------------------|--------|
| HTTP Authorization Scheme: | bearer |

#########################################

Threads scraper
This scraper helps you to scrape posts by a threads user

Here is the sample output of this actor:


{
	"id": "3141737961795561608_314216",
	"reply_count": "27068",
	"user": {
		"profile_pic_url": "https://scontent.cdninstagram.com/v/t51.2885-19/357376107_1330597350674698_8884059223384672080_n.jpg?stp=dst-jpg_s150x150&_nc_ht=scontent.cdninstagram.com&_nc_cat=1&_nc_ohc=euIj8dtTGIkAX-vea85&edm=APs17CUBAAAA&ccb=7-5&oh=00_AfCOXYuDeJ_OxBW9ZYSdlTfCIXdP9NBqDoMVS5rk39mEHA&oe=64ACDDC0&_nc_sid=10d13b",
		"username": "zuck",
		"id": null,
		"is_verified": true,
		"pk": "314216"
	},
	"image_versions2": {
		"candidates": []
	},
	"original_width": 612,
	"original_height": 612,
	"video_versions": [],
	"carousel_media": null,
	"carousel_media_count": null,
	"pk": "3141737961795561608",
	"has_audio": null,
	"text_post_app_info": {
		"link_preview_attachment": null,
		"share_info": {
			"quoted_post": null,
			"reposted_post": null
		},
		"reply_to_author": null,
		"is_post_unavailable": false
	},
	"caption": {
		"text": "70 million sign ups on Threads as of this morning. Way beyond our expectations."
	},
	"taken_at": 1688744372,
	"like_count": 146411,
	"code": "CuZsgfWLyiI",
	"media_overlay_info": null
}



##################

Documentation for JSON Data
The given JSON data represents an threads post with various associated attributes. Below is a breakdown of the individual components and their descriptions:

Main Object
id: The unique identifier for the post.

Type: String
Example: "3141737961795561608_314216"
reply_count: The total number of replies for this post.

Type: String
Example: "27068"
user: The user who created the post. This contains several sub-fields:

profile_pic_url: The URL of the user's profile picture.
Example: A direct link to the image.
username: The username of the user.
Example: "zuck"
id: The unique identifier for the user. (Can be null)
is_verified: A boolean value indicating if the user is verified.
pk: A unique key representing the user.
Type: String
Example: "314216"
image_versions2: An object that lists image versions available for the post.

candidates: An array containing different image versions.
original_width: The original width of the image or video.

Type: Integer
Example: 612
original_height: The original height of the image or video.

Type: Integer
Example: 612
video_versions: An array containing different versions of the video (if the post is a video).

carousel_media: Represents carousel media if the post contains multiple images or videos.

carousel_media_count: The total number of media items in a carousel post.

pk: Another unique key for the post.

Type: String
Example: "3141737961795561608"
has_audio: A boolean value indicating if the post (video) has audio.

text_post_app_info: Contains information related to the text of the post.

link_preview_attachment: Any link preview attached to the post.
share_info: Information related to post sharing.
quoted_post: If the post quotes another post.
reposted_post: If the post is a repost from another user.
reply_to_author: Represents a reply to the post author.
is_post_unavailable: A boolean indicating if the post is unavailable.
caption: Contains the caption of the post.

text: The text content of the caption.
Example: "70 million sign ups on Threads as of this morning. Way beyond our expectations."
taken_at: A timestamp indicating when the post was created (in Unix time format and can be converted to a human-readable date and time format.)

Type: Integer
Example: 1688744372
like_count: The total number of likes for the post.

Type: Integer
Example: 146411
code: A unique code associated with the post.

Type: String
Example: "CuZsgfWLyiI"
media_overlay_info: Contains information related to any media overlays on the post.