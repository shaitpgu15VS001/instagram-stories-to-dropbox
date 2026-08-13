# FastDL investigation record

## Current objective

Prove the next practical step after the verified browser flow: a real Stories JSON can be obtained, the returned media URLs are live, and at least one actual media file can be downloaded successfully without changing production code.

## Current verified architecture

Verified browser flow currently considered authoritative:

1. Open https://fastdl.app/en2/instagram-anonymously-viewer
2. Enter israel_bidur into #search-form-input
3. Click #searchFormButton
4. Clean popup/overlay elements
5. Wait for button.tabs-component__button and click the one whose text contains "Stories"
6. Wait for the browser to issue POST https://api-wh.fastdl.app/api/v1/instagram/stories
7. Capture and parse the JSON response

This is the browser-generated, signed request path. The browser itself creates the request body values including username, ts, _ts, _tsc, _sv, and _s. We do not reverse-engineer _s outside the browser.

## What has been proven

- The real FastDL Stories API request is reachable from the browser path.
- The request body includes the signed fields required by the browser flow.
- The Stories API responds with HTTP 200 and valid JSON payloads.
- The JSON contains real story data and many media URLs.
- The verified browser flow has been reproduced manually at least twice successfully.

## What has been disproven

- It is not true that the Stories API is absent or unusable.
- It is not true that a direct non-browser implementation is required for the Stories request to work.
- It is not true that a failed exploratory POC proves the real flow is broken when the browser flow already works.
- It is not proven that the media URLs are universally downloadable without the browser session or without the exact URL parameters they carry.

## Current hypothesis

The verified browser flow is the correct and required control path. A valid Stories JSON is present, and at least one real media URL from that JSON should be independently downloadable, but the URL may be time-limited, session-specific, or require the browser context to be the same as the one that produced it. The next step is to verify this with a temporary script, without modifying production code.

## Exact successful test scripts

- scripts/debug_fastdl_verified_flow_capture.py
  - Purpose: reproduce the exact browser flow and capture request/response
  - Command: python scripts/debug_fastdl_verified_flow_capture.py --run-id 1
  - Command: python scripts/debug_fastdl_verified_flow_capture.py --run-id 2

- scripts/debug_fastdl_media_download.py
  - Purpose: reuse the verified browser flow, capture Stories JSON, select real media URL(s), and test download behavior
  - Command: python scripts/debug_fastdl_media_download.py --run-id 1

## Exact commands used to run them

- python scripts/debug_fastdl_verified_flow_capture.py --run-id 1
- python scripts/debug_fastdl_verified_flow_capture.py --run-id 2
- python scripts/debug_fastdl_media_download.py --run-id 1

## Important URLs/endpoints

- Viewer: https://fastdl.app/en2/instagram-anonymously-viewer
- Stories API: POST https://api-wh.fastdl.app/api/v1/instagram/stories
- Media host observed in the JSON: https://media.fastdl.app/get
- Story media host observed in the JSON: https://instagram.fist4-1.fna.fbcdn.net/...

## Important selectors

- Username input: #search-form-input
- Search action: #searchFormButton
- Stories tab button: button.tabs-component__button where inner text contains "Stories"
- Visible story content: .media-content--story
- Story timestamp: .media-content__meta-time

## Browser/context configuration

- Browser: Playwright Chromium
- Headless: true
- User agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
- Viewport: 1280x900
- Locale: en-US
- Launch args: --no-sandbox, --disable-dev-shm-usage

## Important request/response structure

Observed Stories request body example:

{
  "username": "israel_bidur",
  "ts": 1786661823233,
  "_ts": 1785411663296,
  "_tsc": 0,
  "_sv": 2,
  "_s": "4c02501e940ce40728d1bde6674cf3ae7ebb44d3da43e5927f69172f451a536b"
}

Observed Stories response summary:

- HTTP status: 200
- Content-Type: application/json; charset=utf-8
- JSON root key: result
- Story count: 28
- Media URL count extracted from the captured JSON: 843
- Media URLs include FastDL-wrapped get URLs and Instagram source URLs

## Relevant timestamps/TTL observations

- The request/response path was captured successfully with browser-generated timestamps.
- The response included signed and expiry-based media URLs such as __sig and __expires parameters.
- The media URLs are not being reverse-engineered here; they are being treated as observed output from the browser flow.
- The observed __expires values are in the same family as time-limited signed URLs, but the exact expiry lifetime is not being decoded or forced in this investigation step.

## Test results

### Verified browser capture, repeated successful

- Script: scripts/debug_fastdl_verified_flow_capture.py
- Run 1: success = true; stories_request_captured = true; stories_response_captured = true; http_status = 200; story_count = 28; media_url_count = 843; JSON parsed = true
- Run 2: success = true; stories_request_captured = true; stories_response_captured = true; http_status = 200; story_count = 28; media_url_count = 843; JSON parsed = true

### Media download proof: first attempt

- Script: scripts/debug_fastdl_media_download.py
- Command: python scripts/debug_fastdl_media_download.py --run-id 1
- Result: failed before Stories response was observed; the script did not yet match the exact verified flow closely enough
- Interpretation: this is not proof that the media URL path is impossible; it is proof that the test script must match the proven browser flow exactly before evaluating the media download step

### Media download proof: successful browser-context download

- Script: scripts/debug_fastdl_media_download.py
- Command: python scripts/debug_fastdl_media_download.py --run-id 3
- Result: success = true; Stories API captured = true; story_count = 28; media_url_count = 252; selected real media URL from the Stories JSON; browser-context download saved a 89,168-byte JPEG; direct HTTP failed under proxy timeout
- Proven: at least one real Stories media URL yielded a valid non-empty file when downloaded via the browser context used to capture the Stories JSON
- Not proven: that a raw direct HTTP request from outside that browser context is always valid; the environment proxy blocked that path here
- Artifacts: scripts/debug_output/fastdl_media_test/run3/browser_context_download.json, scripts/debug_output/fastdl_media_test/run3/direct_http_download.json, scripts/debug_output/fastdl_media_test/run3/stories_response.json, scripts/debug_output/fastdl_media_test/run3/773240222_1101862535837308_7494640496536640791_n.jpg

## Known failures and what they actually mean

- A failed or untriggered POC does not prove the API is absent.
- A POC that does not match the verified flow can fail while the real browser flow still succeeds.
- A missing Stories response in a custom experiment means the interaction sequence was not faithful enough to the proven browser path, not that the FastDL API is invalid.

## Files/artifacts created during investigation

- scripts/debug_fastdl_verified_flow_capture.py
- scripts/debug_fastdl_verified_flow_capture_run1.json
- scripts/debug_fastdl_verified_flow_capture_run2.json
- scripts/debug_fastdl_api_bridge.py
- scripts/debug_fastdl_api_bridge_run1.json
- scripts/debug_fastdl_media_download.py
- scripts/debug_output/fastdl_media_test/ (created as needed by the media-download proof script)

## Production files intentionally NOT modified

- src/main.py
- src/story_downloader.py
- src/rclone_uploader.py
- src/state_manager.py
- src/logger.py
- .github/workflows/sync.yml
- state persistence / rclone / Dropbox pipeline
- existing production FastDL extraction flow

## Current recommended next step

Keep the exact verified browser flow as the control path, then rerun the media-download proof script only after matching the proven flow precisely. Once that succeeds, capture the actual file download result and document whether direct HTTP, browser-context download, or both work. Do not continue into signer reverse-engineering or non-browser reproduction.

## Explicit STOP / DO-NOT-DO items

- Do not modify production code yet.
- Do not modify the FastDL extraction flow.
- Do not modify Dropbox/rclone/state/storage pipeline.
- Do not return to reverse-engineering _s.
- Do not attempt to reproduce the FastDL signer outside the browser.
- Do not replace Playwright with requests/httpx/curl_cffi.
- Do not conclude a failure unless the verified browser flow is faithfully reproduced first.

## Chronological investigation history

### 2026-08-14: verified FastDL Stories API reproduction
- Script: scripts/debug_fastdl_verified_flow_capture.py
- Commands: python scripts/debug_fastdl_verified_flow_capture.py --run-id 1; python scripts/debug_fastdl_verified_flow_capture.py --run-id 2
- Result: both runs succeeded; Stories request captured; Stories response captured; HTTP 200; story_count = 28; media_url_count = 843; JSON parsed = true
- Proven: the real browser path still works and produces the real Stories response.
- Not proven: whether every media URL is independently downloadable or whether the browser session is required for direct media access.
- Artifacts: scripts/debug_fastdl_verified_flow_capture_run1.json, scripts/debug_fastdl_verified_flow_capture_run2.json

### 2026-08-14: first media-download POC
- Script: scripts/debug_fastdl_media_download.py
- Command: python scripts/debug_fastdl_media_download.py --run-id 1
- Result: failed before Stories response was observed
- Proven: a custom script must match the exact verified sequence to trigger the Stories API
- Not proven: that media download is impossible
- Artifacts: none yet from the successful download path; the script did not reach the media stage
- Recommended next step: align the script with the verified browser flow exactly and rerun

### 2026-08-14: debug custom media script truncation issue
- Script: scripts/debug_fastdl_media_download.py
- Command: python scripts/debug_fastdl_media_download.py --run-id 2
- Result: failed during JSON parsing because the script used a truncated sample rather than the full response body from the browser capture
- Proven: the verified browser path still triggers the Stories response; the failure was in the custom extraction logic, not in the API itself
- Not proven: the media URL is non-downloadable
- Artifacts: script corrected to store the full response body before parsing
- Recommended next step: rerun with the full browser-captured response body and proceed to real media-download verification

### 2026-08-14: successful media file download via browser context
- Script: scripts/debug_fastdl_media_download.py
- Command: python scripts/debug_fastdl_media_download.py --run-id 3
- Result: success = true; stories_api_captured = true; story_count = 28; media_url_count = 252; browser-context download saved a non-empty 89,168-byte JPEG; direct HTTP failed under a proxy timeout in this environment
- Proven: a real media URL coming from the captured Stories JSON is directly downloadable when requested from the same Playwright browser context that produced the Stories response
- Not proven: direct HTTP download from a generic client is universally viable or proxy-independent in all environments
- Artifacts: scripts/debug_output/fastdl_media_test/run3/773240222_1101862535837308_7494640496536640791_n.jpg, scripts/debug_output/fastdl_media_test/run3/browser_context_download.json, scripts/debug_output/fastdl_media_test/run3/direct_http_download.json, scripts/debug_output/fastdl_media_test/run3/stories_response.json
- Recommended next step: design a future non-production prototype that uses the browser context or a preserved session to fetch the media, without altering production code

### 2026-08-14: GitHub Actions compatibility probe (headless Chromium, browser flow only)
- Script: scripts/debug_fastdl_github_compatibility.py
- Command: python scripts/debug_fastdl_github_compatibility.py
- Result: Run 1 success = true; elapsed_seconds = 10.424; stories_api_captured = true; json_parsed = true; story_count = 28; media_url_count = 843; downloaded_bytes = 89168; content_type = image/jpeg; file_exists = true. Run 2 success = true; elapsed_seconds = 8.975; stories_api_captured = true; json_parsed = true; story_count = 28; media_url_count = 843; downloaded_bytes = 89168; content_type = image/jpeg; file_exists = true.
- Proven: the same browser-based flow already validated locally is stable across repeated runs under headless Chromium settings similar to GitHub Actions, and it successfully captures the Stories JSON and downloads a real non-empty image.
- Not proven: that every GitHub-hosted runner or every network path will behave identically, because this only approximates the runner environment and does not use a fully provisioned GitHub-hosted runner.
- Artifacts: scripts/debug_output/github_compatibility/run1/trace.json, scripts/debug_output/github_compatibility/run1/stories_response.json, scripts/debug_output/github_compatibility/run1/browser_download_meta.json, scripts/debug_output/github_compatibility/run1/browser_download.jpg; scripts/debug_output/github_compatibility/run2/trace.json, scripts/debug_output/github_compatibility/run2/stories_response.json, scripts/debug_output/github_compatibility/run2/browser_download_meta.json, scripts/debug_output/github_compatibility/run2/browser_download.jpg
- Recommended next step: before any production integration, validate this exact script in a real GitHub Actions runner or a runner-equivalent Linux container; meanwhile treat the flow as broadly compatible in principle, but not yet fully CI-validated.

### 2026-08-14: isolated GitHub verification script (no production modification)
- Script added: scripts/debug_fastdl_github_verified_flow.py
- Workflow added: .github/workflows/fastdl_github_verified_flow.yml
- Goal: reproduce the proven browser flow in a diagnostic-only script, record request/response details, and isolate whether the issue is caused by the GitHub Actions environment versus production integration logic.
- Verified locally: the script ran successfully once with the real target username `israel_bidur`.
- Command executed: $env:PYTHONPATH='.'; python scripts/debug_fastdl_github_verified_flow.py --username israel_bidur
- Result: success = true; input_found = true; input_filled = true; search_click_started = true; search_click_completed = true; stories_tab_found = true; stories_tab_clicked = true; stories_response_seen = true; stories_api_request_seen = true; stories_api_response_seen = true; api_http_status = 200; api_content_type = application/json; charset=utf-8; json_parsed = true; story_count = 28; media_url_count = 843.
- Environment evidence captured by the script: Python 3.12.10; browser user-agent = Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36; viewport = 1280x900; locale = en-US; Chromium version = 148.0.7778.96; platform = Windows-11-10.0.26200-SP0.
- Artifacts saved locally: scripts/debug_output/fastdl_github_verified_flow/run_20260813T233234Z/summary.json, request_metadata.json, response_metadata.json, requestfailed.json, page_errors.json, console_messages.json, page_events.json, run_trace.json, and stories_response.json.
- Interpretation: the exact browser flow is still working locally; this does not prove GitHub Actions will behave identically, but it does prove the script itself is valid and the underlying flow is not broken in the local environment.
- No production files were changed for this verification stage.

## Current classification

At this stage, the local diagnostic success means the issue is not yet proven to be a GitHub-only environment break.

- The flow is not failing locally.
- The dedicated GitHub diagnostic script is ready and can be run on GitHub to answer the environment question directly.
- Until the workflow actually runs on GitHub, the investigation should remain in a pending validation state rather than a concluded environment failure.

## Required next external validation

- Push only the following files for the isolated diagnostic run:
  - scripts/debug_fastdl_github_verified_flow.py
  - .github/workflows/fastdl_github_verified_flow.yml
- Run the workflow named: FastDL GitHub Verified Flow Diagnostic
- Preserve the artifact bundle generated by actions/upload-artifact and compare it against the local run output.
