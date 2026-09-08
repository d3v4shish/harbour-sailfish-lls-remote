# LLs vPlayer Remote Control

An authenticated LAN control service for LLs vPlayer on Sailfish OS. The
service talks to the player's MPRIS interface and is intended to be used by the
Linux Sailfish Phone Control dashboard or another trusted local client.

## What it does

- Runs as the user service `harbour-sailfish-lls-remote.service`.
- Listens on TCP port `8091` by default.
- Requires a bearer token for status and control requests.
- Exposes play, pause, toggle, stop, next, previous, and seek when LLs vPlayer
  is running and exporting MPRIS.

The service does not launch LLs vPlayer. Open the player and load media on the
phone before sending transport commands.

## Pair a Linux client

Obtain the generated token on the phone without printing it into logs:

```sh
harbour-sailfish-lls-remote --show-token
```

Store it in the Linux **Sailfish Phone Control** dashboard's **LLs Remote
token** field, after verifying and trusting the discovered phone. The dashboard
then sends the authenticated requests locally on your behalf.

Direct API example:

```sh
TOKEN='your-token'
curl -H "Authorization: Bearer $TOKEN" http://PHONE:8091/status
curl -X POST -H "Authorization: Bearer $TOKEN" http://PHONE:8091/control/toggle
```

To seek five seconds forward:

```sh
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"delta_ms":5000}' \
  http://PHONE:8091/control/seek
```

## Endpoints

| Request | Purpose |
| --- | --- |
| `GET /discovery` | Unauthenticated endpoint metadata |
| `GET /status` | Current MPRIS status |
| `POST /control/play` | Start playback |
| `POST /control/pause` | Pause playback |
| `POST /control/toggle` | Toggle playback |
| `POST /control/stop` | Stop playback |
| `POST /control/next` | Next item |
| `POST /control/previous` | Previous item |
| `POST /control/seek` | JSON `position_ms` or `delta_ms` |

`/status` and `/control/*` require `Authorization: Bearer TOKEN`.

## Current limits

Loop-mode and volume writes are not wired to LLs vPlayer's actual state in the
supported player version, so they return `501 unsupported_command` rather than
claiming success. A missing or closed player returns an explicit `no_adapter`
response.

## Build and test

The package is Python-based and builds as a noarch Sailfish RPM. Run its local
test suite with:

```sh
python3 -B tests/self_test.py
```

## License

MIT. See [LICENSE](LICENSE).
