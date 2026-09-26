## ADDED Requirements

### Requirement: The client keeps the token out of its URLs
Once loaded, the client SHALL remove the token from the address shown
in the browser, and SHALL NOT put the token on the URL of any request
it makes — page resources, control requests, the marker-sheet link, or
the frame socket — relying on the session cookie the server issued
instead. A URL is copied into browser history, server logs and
screenshots; a cookie is not. Where the server refuses the frame
socket for want of a valid credential, the client SHALL say so and
direct the person to reopen the URL the server printed, since a stale
cookie from an earlier server run looks exactly like a missing one.

#### Scenario: The address bar is cleaned after load
- **WHEN** the client page is opened from a URL carrying the token
- **THEN** the address shown in the browser no longer carries the token,
  and every other part of the address is preserved

#### Scenario: Requests carry no token in their URLs
- **WHEN** the client fetches its script, reads or changes a setting, or
  opens the frame socket
- **THEN** none of those request URLs carries the token, and each is
  authorized by the session cookie

#### Scenario: A refused socket explains how to recover
- **WHEN** the server closes the frame socket with a policy-violation
  status
- **THEN** the page states that the credential was missing or invalid
  and to reopen the exact URL the server printed
