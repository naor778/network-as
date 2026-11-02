# Network simulation: TCP and Reliable UDP

Educational Python networking project with simulated DHCP/DNS discovery and file downloads over TCP and a custom reliable UDP protocol.

## Components

- DHCP simulation: JSON messages over UDP, address pool, expiring leases.
- DNS simulation: JSON messages over UDP, service lookup and TTL metadata.
- Origin server: serves sample files over HTTP/TCP.
- TCP application server: forwards requests to the origin.
- RUDP application server: sequence numbers, ACKs, retransmission, receive window and simplified congestion window, with optional loss/delay simulation.

DHCP/DNS here are teaching simulations, not implementations of their standard wire protocols. Assigned IPs are simulated; operating system network settings are not changed.

## Run

Requires Python 3.9 or newer (validated with Python 3.12); no third-party packages.
On Windows, use `py` instead of `python3` if needed.
From the project root, run each server in a separate terminal:

```sh
python3 -m dhcp_server.dhcp_server
python3 -m dns_server.dns_server
python3 -m app_server.origin_server
python3 -m app_server.app_server_tcp
python3 -m app_server.app_server_rudp
```

Then run either client from the project root and select a file:

```sh
python3 -m client.client_tcp
python3 -m client.client_rudp
```

Downloads are saved in the current directory as `downloaded_<filename>` or `downloaded_rudp_<filename>`.
Configuration is in `config/config.json`. Defaults bind to loopback only; TCP ports: 8080/8081; UDP ports: 6767/53555/9090. RUDP bind address/port are also hardcoded in its server module.

## Validation

Both clients were exercised through DHCP/DNS discovery, listing and downloading `hello.txt` and `test.txt` against all five running services. TCP downloads matched the original bytes; RUDP downloads matched text (Python normalizes line endings). Packet-loss/delay scenarios have not been validated.

Run the file-access regression tests from the project root:

```sh
python3 -m unittest discover -s tests -v
```

Five regression tests pass, covering normal downloads, missing files, parent-directory traversal, similarly named sibling directories, and external symbolic links.

## Limitations

Use locally for learning. The origin server resolves requested paths and rejects access outside `app_server/files`, including symbolic links pointing outside it. Do not expose these services to an untrusted network. Additional improvements include malformed-message handling, timeouts for DHCP/DNS, bounded server retries and binary-safe RUDP transfers. Servers process requests sequentially. There is no authentication or encryption.
