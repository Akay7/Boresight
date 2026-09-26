## ADDED Requirements

### Requirement: The client identifies itself when its connection opens
The client SHALL send a `hello` control message identifying itself as a
phone, with the capture resolution it was granted, each time its frame
connection opens, including after a reconnect. With more than one kind
of client able to connect, the server's logs and session listing are
otherwise unable to say which device a session belongs to.

#### Scenario: Hello is sent on connect
- **WHEN** the client's frame connection opens
- **THEN** it sends a `hello` message naming the client kind `phone` and
  the granted capture resolution before or alongside its first frame

#### Scenario: Hello is re-sent after a reconnect
- **WHEN** the connection is re-established
- **THEN** the client sends `hello` again on the new connection
