# QA cases: llm-client

### QA-001 Per-agent model sent for bureaucracy_assistant
- Covers: Business Goals, Gherkin scenario 1, T3
- Type: functional
- Given LLM_MODEL=global-m, LLM_MODEL_BUREAUCRACY_ASSISTANT=qwen2.5-3b, LLM_BASE_URL=http://llm.local:8080/v1, and a mock server that returns "Hello"
- When the caller sends chat("bureaucracy_assistant", [{"role":"user","content":"Hi"}])
- Then the server receives a POST body with model "qwen2.5-3b" and the caller gets the string "Hello"

### QA-002 Per-agent model sent for document_processor
- Covers: Gherkin scenario 2, Edge Cases (agent names)
- Type: functional
- Given LLM_MODEL=global-m, LLM_MODEL_DOCUMENT_PROCESSOR=phi-3-mini, and a mock server
- When the caller sends chat("document_processor", [{"role":"user","content":"Summarize"}])
- Then the server receives model "phi-3-mini"

### QA-003 Global model fallback
- Covers: Technical Constraints (fallback), T2
- Type: functional
- Given LLM_MODEL=global-m and no LLM_MODEL_ANALYSIS
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then the server receives model "global-m"

### QA-004 Per-agent base URL, timeout and key override the global values
- Covers: Technical Constraints (per agent values), T2
- Type: functional
- Given LLM_BASE_URL=http://a.local/v1, LLM_BASE_URL_ANALYSIS=http://b.local/v1, LLM_API_KEY=g-key, LLM_API_KEY_ANALYSIS=a-key
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then the request goes to http://b.local/v1/chat/completions with header "Authorization: Bearer a-key"

### QA-005 Request URL and answer extraction
- Covers: Technical Constraints (request and answer)
- Type: functional
- Given base URL http://llm.local:8080/v1 and a server that returns {"choices":[{"message":{"content":"42"}}]}
- When the caller sends chat("legal_research", [{"role":"user","content":"Q"}])
- Then the request is a POST to http://llm.local:8080/v1/chat/completions with only the keys "model" and "messages", and the result is "42"

### QA-006 Trailing slash stripped
- Covers: Technical Constraints (trailing slash)
- Type: edge
- Given base URL http://llm.local:8080/v1/
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then the request goes to http://llm.local:8080/v1/chat/completions with no double slash

### QA-007 Empty API key sends no Authorization header
- Covers: Edge Cases (empty API key)
- Type: edge
- Given LLM_API_KEY is empty and no per-agent key
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then the request has no Authorization header

### QA-008 Unknown agent name
- Covers: Edge Cases (unknown agent), Gherkin scenario 5
- Type: failure
- Given a mock server that counts requests
- When the caller sends chat("astrologer", [{"role":"user","content":"Hi"}])
- Then LLMConfigError is raised with the text "astrologer" and the server received 0 requests

### QA-009 Old alias names rejected
- Covers: Edge Cases (no alias)
- Type: negative
- Given the mock server counts requests
- When the caller sends chat("bureaucracy", [{"role":"user","content":"Hi"}]) and chat("processor", ...)
- Then each call raises LLMConfigError naming the agent and 0 requests are sent

### QA-010 Agent with no model
- Covers: Edge Cases (no model)
- Type: failure
- Given LLM_MODEL is empty and LLM_MODEL_CHANGE_TRACKER is empty
- When the caller sends chat("change_tracker", [{"role":"user","content":"Hi"}])
- Then LLMConfigError is raised naming "change_tracker" and the variable LLM_MODEL_CHANGE_TRACKER, and 0 requests are sent

### QA-011 Empty messages list
- Covers: Edge Cases (empty messages)
- Type: failure
- Given a configured agent "analysis" and a counting mock server
- When the caller sends chat("analysis", [])
- Then ValueError is raised and 0 requests are sent

### QA-012 Response body larger than 1 MiB
- Covers: Edge Cases (1 MiB cap)
- Type: edge
- Given a server that returns a 1 MiB + 1 byte (1048577 bytes) body with status 200
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then LLMError is raised

### QA-013 Response body exactly 1 MiB accepted
- Covers: Edge Cases (1 MiB cap, boundary)
- Type: edge
- Given a server that returns a valid JSON body of exactly 1048576 bytes with content in choices[0].message.content
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then the content string is returned and no error is raised

### QA-014 Base URL with credentials
- Covers: Edge Cases (base URL checks)
- Type: security
- Given LLM_BASE_URL=http://user:pass@llm.local/v1
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then LLMConfigError is raised naming "analysis", the text holds neither "pass" nor the URL, and 0 requests are sent

### QA-015 Base URL with query
- Covers: Edge Cases (base URL checks)
- Type: security
- Given LLM_BASE_URL=http://llm.local/v1?key=abc
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then LLMConfigError is raised naming "analysis" and 0 requests are sent

### QA-016 Base URL with fragment
- Covers: Edge Cases (base URL checks)
- Type: security
- Given LLM_BASE_URL=http://llm.local/v1#frag
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then LLMConfigError is raised naming "analysis" and 0 requests are sent

### QA-017 Base URL with non-http scheme
- Covers: Edge Cases (base URL checks)
- Type: security
- Given LLM_BASE_URL=ftp://llm.local/v1 (and a second run with file:///etc/x)
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then LLMConfigError is raised naming "analysis" and 0 requests are sent

### QA-018 http scheme allowed for local servers
- Covers: Decision (http stays allowed)
- Type: functional
- Given LLM_BASE_URL=http://localhost:11434/v1
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then the request is sent and the answer is returned

### QA-019 Missing or empty base URL
- Covers: Edge Cases (base URL checks), OPEN item
- Type: failure
- Given LLM_BASE_URL is empty and no per-agent URL
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then LLMConfigError names "analysis" and 0 requests are sent (decided in spec T2: an empty base URL is a config error)

### QA-020 No choices in response
- Covers: Edge Cases (bad response)
- Type: failure
- Given a server that returns status 200 and {"choices":[]}
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then LLMError is raised with status_code 200

### QA-021 Missing choices key
- Covers: Edge Cases (bad response)
- Type: failure
- Given a server that returns status 200 and {"id":"x"}
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then LLMError is raised with status_code 200

### QA-022 Non-string content
- Covers: Edge Cases (bad response)
- Type: failure
- Given a server that returns status 200 and {"choices":[{"message":{"content":null}}]}
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then LLMError is raised with status_code 200

### QA-023 Non-JSON body
- Covers: Edge Cases (bad response)
- Type: failure
- Given a server that returns status 200 and the body "<html>oops</html>"
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then LLMError is raised with status_code 200

### QA-024 Timeout value not positive number (global)
- Covers: Edge Cases (timeout value), T1
- Type: failure
- Given LLM_TIMEOUT=abc (repeat with 0, -1, nan, inf)
- When Settings reads llm_timeout
- Then ValueError is raised naming LLM_TIMEOUT

### QA-025 Per-agent bad timeout
- Covers: Edge Cases (timeout value), T2
- Type: failure
- Given LLM_TIMEOUT_ANALYSIS=-5 and LLM_TIMEOUT=30
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then ValueError is raised naming LLM_TIMEOUT_ANALYSIS and 0 requests are sent

### QA-026 Default timeout and whitespace
- Covers: Technical Constraints, T1
- Type: edge
- Given LLM_TIMEOUT unset, then LLM_TIMEOUT=" 0.2 "
- When Settings reads llm_timeout
- Then it returns 60.0 for the first case and 0.2 for the second

### QA-027 Timeout metric
- Covers: Failure Modes (slow server), Success Metrics (0.2 s timeout)
- Type: performance
- Given LLM_TIMEOUT=0.2 and a server that waits 5 s before it answers
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then LLMTimeoutError is raised within 1.25 s

### QA-028 Slow trickle body
- Covers: Failure Modes (slow server), Decision (deadline)
- Type: performance
- Given LLM_TIMEOUT=0.2 and a server that sends one byte every 0.1 s for 5 s
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then LLMTimeoutError is raised within 1.25 s

### QA-029 LLMTimeoutError is an LLMError
- Covers: Failure Modes, Decision (errors)
- Type: functional
- Given a timeout occurs
- When the caller catches LLMError
- Then the catch succeeds, and LLMConfigError is not caught by "except LLMError"

### QA-030 HTTP 500
- Covers: Failure Modes (non-2xx), Gherkin scenario 4
- Type: failure
- Given a server that returns status 500 and body {"error":"boom for secret prompt"}
- When the caller sends chat("analysis", [{"role":"user","content":"my secret prompt"}])
- Then LLMError is raised with status_code 500

### QA-031 Other non-2xx codes
- Covers: Failure Modes (non-2xx)
- Type: failure
- Given a server that returns 401, then 429, then 404
- When the caller sends chat("analysis", ...) for each
- Then each call raises LLMError with status_code 401, 429, 404 and the server received exactly 1 request per call (no retry)

### QA-032 No secrets in error text
- Covers: Success Metrics (0 occurrences), Failure Modes
- Type: security
- Given LLM_API_KEY=sk-test-123, LLM_BASE_URL=http://llm.local:8080/v1, message content "my secret prompt", and servers that return 500, a bad body, an oversize body, and a timeout
- When each chat call fails
- Then no error text contains "sk-test-123", "llm.local" or "my secret prompt"

### QA-033 Connection refused
- Covers: Failure Modes (transport error)
- Type: failure
- Given the transport raises a connection error
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then LLMError is raised with status_code None, and the text holds no base URL or key

### QA-034 No retry on failure
- Covers: Failure Modes (no retry)
- Type: failure
- Given a server that returns 503 and counts requests
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then LLMError is raised and the server counted exactly 1 request

### QA-035 Redirect is not followed
- Covers: Technical Constraints (follow_redirects=False)
- Type: security
- Given a server that returns 302 with Location http://evil.local/
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then LLMError is raised with status_code 302 and exactly 1 request was sent

### QA-036 Proxy environment ignored
- Covers: Technical Constraints (trust_env=False)
- Type: security
- Given HTTP_PROXY=http://proxy.local:3128 in the process environment
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then the request goes to the configured base URL and not to the proxy

### QA-037 No logging of key or content
- Covers: Technical Constraints (no log line)
- Type: security
- Given log capture is on, key "sk-test-123", content "my secret prompt"
- When a successful call and a failed call finish
- Then the captured logs hold neither value

### QA-038 Repeated calls
- Covers: Negative (repeated actions)
- Type: edge
- Given one client and a server that answers "A", then "B"
- When the caller sends chat("analysis", ...) twice with the same messages
- Then the results are "A" then "B", and 2 requests were sent

### QA-039 Messages sent unchanged, including non-ASCII
- Covers: Technical Constraints (request body)
- Type: edge
- Given messages [{"role":"system","content":"Jesteś asystentem"},{"role":"user","content":"Ile kosztuje wiza?"}]
- When the caller sends chat("legal_research", messages)
- Then the server receives the same two messages in the same order with the same text

### QA-040 Agent list matches Settings
- Covers: Decision (LLM_AGENTS)
- Type: functional
- Given the seven llm_model_* properties of Settings
- When the agent list is compared with those names
- Then both sets hold exactly document_fetcher, document_processor, legal_research, change_tracker, knowledge_graph, analysis, bureaucracy_assistant

### QA-041 Every one of the seven agents works
- Covers: Technical Constraints (seven names)
- Type: functional
- Given LLM_MODEL_<AGENT>=m-<agent> for all seven names
- When the caller sends chat(<agent>, [{"role":"user","content":"Hi"}]) for each
- Then each server request holds model "m-<agent>"

### QA-042 Existing LLM_MODEL_<AGENT> properties unchanged
- Covers: Technical Constraints, T1
- Type: functional
- Given LLM_MODEL_ANALYSIS=x1 and LLM_MODEL=g
- When Settings reads llm_model_analysis and llm_model
- Then they return "x1" and "g" as before

### QA-043 Settings lookup with both unset
- Covers: T1
- Type: edge
- Given neither LLM_API_KEY_ANALYSIS nor LLM_API_KEY is set
- When Settings does llm_setting("API_KEY", "analysis")
- Then the result is an empty string

### QA-044 Fake ChatModel satisfies port
- Covers: Decision (ChatModel port), T2
- Type: functional
- Given a test class with chat(agent_name, messages) -> str
- When an agent test passes it where a ChatModel is expected
- Then it type-checks with 0 pyright errors and returns its canned string

### QA-045 Settings is a leaf
- Covers: Decision (config stays leaf), Technical Constraints
- Type: functional
- Given a fresh import of Settings
- When Settings reads an invalid LLM_TIMEOUT
- Then only ValueError is raised, never an LLM error type

### QA-046 Resource budget
- Covers: Technical Constraints (budget)
- Type: performance
- Given a process that makes 100 calls in sequence against a mock server
- When the calls finish
- Then no new thread remains and no model weights are loaded (memory growth below 50 MB)

### QA-047 Line coverage metric
- Covers: Success Metrics (100 % coverage)
- Type: performance
- Given the unit tests of the llm package
- When coverage runs on src/core/llm
- Then line coverage is 100 %

### QA-048 Quality gate metric
- Covers: Success Metrics (quality gate), T4
- Type: functional
- Given the finished change
- When ruff check, ruff format --check, pyright and pytest -m "not integration" run
- Then all four exit 0 with 0 errors

### QA-049 Gherkin scenarios count
- Covers: Success Metrics (5 of 5)
- Type: functional
- Given the five issue scenarios (QA-001, QA-002, QA-027, QA-030, QA-008)
- When the unit tests run with a mock transport
- Then 5 of 5 pass

### QA-050 Non-JSON-object body types
- Covers: Edge Cases (bad response)
- Type: failure
- Given a server that returns status 200 and the JSON body [1,2,3]
- When the caller sends chat("analysis", [{"role":"user","content":"Hi"}])
- Then LLMError is raised with status_code 200
