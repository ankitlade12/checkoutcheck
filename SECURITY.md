# Security

CheckoutCheck currently supports a trusted single operator on localhost or through an IAM-authorized AWS Session Manager tunnel. It has no public-user authentication or tenant isolation. Do not expose its write API directly to the internet or run it with multiple server workers.

Keep AWS credentials outside source and containers. Private media, databases, model weights and operational artifacts belong in ignored private storage. The inference/reference separation is not a sandbox for hostile executable adapters.

To report a vulnerability, use GitHub's private vulnerability reporting feature if it is enabled for this repository. Otherwise contact the maintainer privately through their GitHub profile before sharing details. Do not disclose secrets, private recordings or exploit payloads in a public issue.

No formal security audit or production-service support commitment is claimed. See the [roadmap](docs/roadmap.md) for the isolation, data-governance and operational requirements of a future community pilot.
