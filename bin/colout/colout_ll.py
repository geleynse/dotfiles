def theme():
    p="([rwxs-])"
    reg="^([ld-])"+p*9+"\s.*$"
    colors="blue"+",green"*3+",yellow"*3+",red"*3
    styles="normal"+ ",normal,bold,normal"*3
    return [ [reg, colors, styles] ]

