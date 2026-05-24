def theme():
    info="cyan"
    success="green"
    warning="yellow"
    error="red"
    return [
        [ "^.*BUILD SUCCESS.*$", success, "bold" ],
        [ "^.*SUCCESS \[.*$", success, "bold" ],
        [ "^.*BUILD ERROR.*$", error, "bold" ],
        [ "^.*FAILURE \[.*$", error, "bold" ],
        [ "^\[ERROR\]", error, "bold" ],
        [ "^\[WARNING\]", warning ],
        [ "^.*SKIPPED \[.*$", info ],
        [ "^\[INFO\]", info ]
    ]

