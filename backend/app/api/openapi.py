"""Text published in the OpenAPI document for MCP and other agents."""

OPENAPI_DESCRIPTION = """
JSON API for the Aurelia Fleet manual assistant.

Every JSON response uses the same envelope: session_auth, errors, success, and data.
When success is false, data is null and errors[0].msg explains the failure,
except ask_question when the model provider is down: that 503 still puts the retrieved
passages in data.citations. There is no top-level detail property.

An MCP adapter should expose each operationId as one tool and fill arguments only from this schema.

upload_document is multipart. The file field is the manual. The metadata field is a JSON
string matching DocumentUploadRequest. equipmentModel, maker, and title may be omitted.
When they are omitted, the server reads them from the file. describe_document returns those
names without storing the file, so a client can show them before upload_document.
Uploading the same bytes again for the same tenant returns the existing job and does not
queue a second ingest. data.duplicate is true in that case.

get_job reports pending, processing, completed, or failed. failureReason is set only when failed.
Poll it until the status is completed or failed. Do not send a JSON body on GET.

list_makers searches the makers already stored. list_equipment_models does the same for equipment models.
q is the text typed so far. An empty q returns every stored name.
Use the returned spelling when uploading so the same maker or model is not stored twice under a typo.

list_documents has no JSON body. equipmentModel is an optional query filter.
offset is a page number starting at 1. Follow data.next.

download_document returns the original file for a documentId. The body is the file bytes,
streamed in chunks, not the JSON envelope. A missing id is still the error envelope with 404.

list_aliases, create_alias, update_alias, and delete_alias manage groups of words that mean the same feature.
A group such as bluetooth and ble makes either word find the other. Each word belongs to one group.
update_alias replaces the whole list. delete_alias removes the group.

ask_question searches the tenant library. Set equipmentModel to restrict retrieval.
When the manuals do not contain the answer, success is true, data.answered is false,
and data.refusalReason explains the refusal. Do not invent a fact from that response.

Authorization is an optional Authorization: Bearer header carrying an HS256 JWT.
The token payload includes session_auth.tenantId. When AUTH_REQUIRED is false the header
may be omitted and the default tenant is used.
Do not retry 400, 401, 404, 413, or 422 until the arguments change.
502 and 503 may be retried once.
"""

OPENAPI_TAGS = [
    {
        "name": "Status",
        "description": "Process liveness. get_service_status does not list manuals.",
    },
    {
        "name": "Documents",
        "description": "Upload a manual, list manuals visible to the tenant, and download an original file.",
    },
    {
        "name": "Jobs",
        "description": "Poll ingest status. completed means the manual can be searched.",
    },
    {
        "name": "Answers",
        "description": "Ask a question. The answer cites retrieved passages or refuses.",
    },
    {
        "name": "Aliases",
        "description": "Words that search treats as one feature. Edited per tenant.",
    },
]
