# [Get all possible keywords](https://www.vertica.com/docs/12.0.x/HTML/Content/Authoring/SQLReferenceManual/SystemTables/CATALOG/KEYWORDS.htm)
# KEYWORDS = "SELECT keyword FROM keywords WHERE reserved = 'R' ;"
#
# [CTE structure](https://www.vertica.com/docs/12.0.x/HTML/Content/Authoring/SQLReferenceManual/Statements/SELECT/WITHClause.htm)
# WITH... with-query-1 [(col-name[,…])]AS (SELECT…),
#     with-query-2 [(col-name[,…])]AS (SELECT… [with-query-1]),
# .
# .
# .
#     with-query-n [(col-name[,…])]AS (SELECT… [with-query-1, with-query-2, with-query-n[,…]])
#
# [Select statement structure](https://www.vertica.com/docs/12.0.x/HTML/Content/Authoring/SQLReferenceManual/Statements/SELECT/SELECT.htm)
# [ AT epoch ] SELECT [ /*+ LABEL(label‑name)*/ ] [ ALL | DISTINCT ]
# ... { * | expression [ [AS] output-name] }[,…]
# ... [ into-table-clause ]
# ... [ from-clause ]
# ... [ where‑clause ]
# ... [ time‑series‑clause ]
# ... [ group‑by‑clause[,…] ]
# ... [ having-clause[,…] ]
# ... [ match-clause ]
# ... [ UNION { ALL | DISTINCT } ]
# ... [ except‑clause ]
# ... [ intersect‑clause ]
# ... [ ORDER BY expression { ASC | DESC }[,…] ]
# ... [ LIMIT { count | ALL } ]
# ... [ OFFSET start‑row ]
# ... [ FOR UPDATE [ OF table-name[,…] ] ]

import re
from pathlib import Path

import click

# Just ones we typically care about:
ORDERED_GROUPS = (
    "WITH",
    "SELECT",
    "INTO",
    "FROM",
    "WHERE",
    "TIMESERIES",
    "GROUP BY",
    "HAVING",
    "MATCH",
    "UNION",
    "EXCEPT",
    "INTERSECT",
    "ORDER BY",
    "LIMIT",
    "OFFSET",
    "FOR UPDATE",
)


def process_from(x: str, current_line_length: int, max_line_length: int, indent: str) -> str:
    # we don't really need to split it like this
    # since we just stick it back together
    # split_table_name = x.strip().split(' ')
    # table_name = split_table_name[0]
    # if len(split_table_name) == 2:
    #     alias = ' ' + split_table_name[1]
    # else:
    #     alias = ''
    # together = table_name + alias
    together = x.strip()
    if len(together) + 1 + current_line_length <= max_line_length:
        return " " + together + "\n"
    else:
        return "\n" + indent + together + "\n"


def process_where(x: str, current_line_len: int, max_line_len: int, indent: str) -> str:
    # we don't really need to split it like this
    # since we just stick it back together
    clauses = [z.strip() for z in x.strip().split("and")]
    oneline = " AND ".join(clauses)
    if len(oneline) + 1 + current_line_len <= max_line_len:
        return " " + oneline + "\n"
    else:
        return "\n" + f"\n{indent}AND ".join(clauses) + "\n"


def scan_to_close(remaining_text: str, open_char: str = "(", close_char: str = ")") -> str:
    needed_to_close: int = 1
    i: int = 0
    while needed_to_close > 0 and i < len(remaining_text):
        if remaining_text[i] == close_char:
            needed_to_close -= 1
        if remaining_text[i] == open_char:
            needed_to_close += 1
        i += 1
    if needed_to_close > 0:
        raise RuntimeError("Unbounded group")
    return remaining_text[: i - 1]


def test_scan_to_close() -> None:
    assert scan_to_close("a)") == "a"
    assert scan_to_close("(a))") == "(a)"
    import unittest

    unittest.TestCase().assertRaises(RuntimeError, scan_to_close, "(a)")
    assert scan_to_close("(z(x(a)1)2)3)") == "(z(x(a)1)2)3"


def detect_substatement_type(substatement: str) -> str:
    if len(substatement.strip()) > 6 and substatement.strip().upper()[:6] == "SELECT":
        return "select"
    # lists of numbers:
    elif re.match(r"[0-9*\.]+", substatement.strip()) is not None:
        return "list"
    # lists of strings:
    elif re.match(r"'.*?'\s*,", substatement.strip()) is not None:
        return "list"
    # everything else:
    else:
        return "generic"


def test_detect_substatement_type() -> None:
    detect_substatement_type("select x from z") == "select"
    detect_substatement_type("x, y, z") == "list"
    detect_substatement_type("'x', 'y', 'z'") == "list"
    detect_substatement_type("1, 2, 3") == "list"
    detect_substatement_type("case when ... then else end as z") == "generic"
    detect_substatement_type("case when x in (z, y, j) then else end as z") == "generic"
    detect_substatement_type("z == 10 and y = 5") == "generic"


def indent_case_statement(stmt: str, cur_ind: str, ind: str, max_ll, debug: bool = False) -> str:
    for keyword in {"CASE", "WHEN", "THEN", "ELSE", "END", "AS", "NULL", "IN"}:
        stmt = stmt.replace(" " + keyword.lower() + " ", " " + keyword + " ")

    # first, get out to the end
    match = re.match("CASE(?P<body>.*?) END (?P<end>.*)", stmt, re.IGNORECASE).groupdict()
    if debug:
        print(match)
    # if there is an else, get that
    if len(split := match["body"].split(" ELSE ")) > 1:
        body = split[0]
        elsestmt = split[1]
    else:
        body = match["body"].strip()
        elsestmt = None
    stmts = [("WHEN", x.strip()) for x in body.split("WHEN ") if x.strip() != ""]
    if elsestmt is not None:
        stmts.append(("ELSE", elsestmt))
    if debug:
        print(stmt)
        print(match)
        print(body, elsestmt)
        print(stmts)
    if (
        len(cur_ind)
        + 5
        + len(flat := " ".join([f"{k} {v}" for k, v in stmts]))
        + 5
        + len(match["end"])
        <= max_ll
    ):
        return "CASE " + flat + " END " + match["end"]
    else:
        return (
            f"CASE\n{cur_ind}{ind}"
            + f"{cur_ind}{ind}".join([f"{k} {v}\n" for k, v in stmts])
            + f"{cur_ind}{ind}END "
            + match["end"]
        )


def test_indent_case_statement() -> None:
    assert (
        indent_case_statement(
            "case when x = 10 then 5 when z = 3 then 2 else 20 end as test",
            " " * 4,
            " " * 4,
            1000,
        )
        == "CASE WHEN x = 10 THEN 5 WHEN z = 3 THEN 2 ELSE 20 END AS test"
    )
    assert (
        indent_case_statement(
            "case when x = 10 then 5 when z = 3 then 2 else 20 end as test",
            "",
            " " * 4,
            20,
        )
        == """CASE
    WHEN x = 10 THEN 5
    WHEN z = 3 THEN 2
    ELSE 20
    END AS test"""
    )
    assert (
        indent_case_statement(
            " case when z in (1, 2, 3) then 0 when z = 10 then 20 else null end as q ".strip(),
            " " * 4,
            " " * 4,
            20,
        )
        == """CASE
        WHEN z IN (1, 2, 3) THEN 0
        WHEN z = 10 THEN 20
        ELSE NULL
        END AS q"""
    )


def parse(  # noqa: C901
    text: str, line_length=100, debug: bool = False, indent=" " * 4, starting_indent: str = ""
) -> str:
    # select_block = re.search('$|\n|\s+SELECT\n|\s+', 'SELECT ')
    # join_block = None
    # tail_blocks = None
    # re.match('\s*(?P<select>SELECT)\s*(?P<expressions>.*?)\s*(?P<from>FROM)\s*(?P<tablename>[a-zA-Z]+[a-zA-Z0-9_]*)\s*?(?P<joins>(?P<join>(LEFT JOIN)|(OUTER JOIN))\s+(?P<jointablename>[a-zA-Z]+?[a-zA-Z0-9_]*)\s*){1,2}', 'SELECT FROM mytable LEFT JOIN othertable1 LEFT JOIN othertable2').groups()

    # Sanitize the text to only have single-space separators
    # assert re.sub('\s+|\n', ' ', '   x  y z \n  x   '.strip()) == 'x y z x'
    # sanitized = re.sub(r"\s+", " ", text.strip())
    # keep newlines, so as to be less aggressive
    # just remove multiple spaces
    sanitized = re.sub(r"[ \t]+", " ", text.strip())
    # and all indentation:
    sanitized = re.sub(r"\n[ \t]+", "\n", sanitized)
    if debug:
        print(sanitized)

    # TODO:
    # If a lone-line comment is detected, don't try to combine lines before/after it
    # Combine end of line comments when combining statements
    # Try sqlparse on my examples
    #    Looking at the code, they specifically capture A LOT of tokens
    #    reindent='aligned' is what I liked before
    # Here, going for more of the black approach

    # Parameters for the loop
    current_ll = starting_indent
    current_clause = None
    current_indent = starting_indent
    formatted = ""
    buffer = ""
    expressions = []
    i = 0
    while i < len(sanitized):
        buffer += sanitized[i]
        if sanitized[i] == "(":
            paren_contains = scan_to_close(sanitized[i + 1 :])
            # paren_type = detect_substatement_type(paren_contains)
            # if paren_type == 'list':
            # just skip everything in parens for now (leave completely as-is)
            i += len(paren_contains) + 1
            buffer += paren_contains + ")"
        if debug:
            print(f"{i=}, {sanitized[i]=}, {current_clause=}, {current_ll=}, {buffer=}")

        if current_clause == "select":
            if sanitized[i] == ",":
                if debug:
                    print(f"found an expression: {buffer[:-1]=}")
                if buffer[:-1].strip().lower()[:4] == "case":
                    indented_statement = indent_case_statement(
                        buffer[:-1].strip(), indent, indent, line_length
                    )
                else:
                    indented_statement = buffer[:-1].strip()
                expressions.append(indented_statement)
                buffer = ""
            select_exits = {"FROM", "INTO"}
            if (exit := buffer.upper()[-4:]) in select_exits:
                if buffer[:-4].strip().lower()[:4] == "case":
                    expressions.append(
                        indent_case_statement(buffer[:-4].strip(), indent, indent, line_length)
                    )
                else:
                    expressions.append(buffer[:-4].strip())
                if exit == "FROM":
                    if len(", ".join(expressions)) + current_ll + 1 <= line_length:
                        formatted += " " + ", ".join(expressions) + "\n"
                    else:
                        # this puts the first expression on the SELECT line
                        # formatted += ' ' + f',\n{indent}'.join(expressions) + '\n'
                        # this starts it on a new line:
                        formatted += f"\n{indent}" + f",\n{indent}".join(expressions) + "\n"
                    formatted += exit
                    current_ll, current_clause, buffer = len(exit), exit.lower(), ""
                elif exit == "INTO":
                    raise RuntimeError("No support for INTO clause")
        if current_clause == "from":
            # NATURAL [ INNER | LEFT OUTER | RIGHT OUTER | FULL OUTER ] JOIN right-join-table
            join_starts = {"NATURAL", "INNER", "LEFT", "RIGHT", "FULL", "CROSS", "JOIN"}
            exits = join_starts | set(ORDERED_GROUPS[4:])
            if i == (len(sanitized) - 1):
                formatted += process_from(buffer, current_ll, line_length, indent)
            else:
                for exit in exits:
                    if len(buffer) >= len(exit) and buffer[-len(exit) :].upper() == exit:
                        formatted += process_from(
                            buffer[: -len(exit)], current_ll, line_length, indent
                        )
                        formatted += exit
                        current_ll, current_clause, buffer = len(exit), exit.lower(), ""
        if current_clause == "where":
            # NATURAL [ INNER | LEFT OUTER | RIGHT OUTER | FULL OUTER ] JOIN right-join-table
            exits = set(ORDERED_GROUPS[5:])
            if i == (len(sanitized) - 1):
                formatted += process_where(buffer, current_ll, line_length, indent)
            else:
                for exit in exits:
                    if len(buffer) >= len(exit) and buffer[-len(exit) :].upper() == exit:
                        formatted += process_where(buffer[: -len(exit)], current_ll, line_length)
                        formatted += exit
                        current_ll, current_clause, buffer = len(exit), exit.lower(), ""
        if (x := buffer.upper()) == "SELECT":
            formatted += x
            current_indent += indent
            current_ll, current_clause, buffer = len(x), x.lower(), ""
        i += 1

    return formatted


def test_parse_wrapper(raw: str, expected: str, debug: bool, **kwargs) -> None:
    print("=" * 80)
    print("=" * 80)
    parsed = parse(raw, debug=debug, **kwargs)
    # Mark the end of the debug output from parse()
    if debug:
        print("=" * 80)
    print(raw)
    print("=" * 80)
    print(expected)
    # Show the first character where they are different,
    # since it's about to fail:
    if parsed != expected:
        for i in range(len(expected)):
            if expected[i] != parsed[i]:
                print(f"{i=}, {expected[i]=}, {parsed[i]=}")
                break
    assert parsed == expected


def test_parse():
    debug = True

    raw = """select *, a, b,z from my_table q where h and k > 10"""
    expected = """SELECT *, a, b, z
FROM my_table q
WHERE h AND k > 10
"""
    test_parse_wrapper(raw, expected, debug)

    raw = """select *, a, b,z,somethingreallylongsoitdoesntfitononelineanymore from my_table q where h and k > 10"""
    expected = """SELECT
    *,
    a,
    b,
    z,
    somethingreallylongsoitdoesntfitononelineanymore
FROM my_table q
WHERE h AND k > 10
"""
    test_parse_wrapper(raw, expected, debug, line_length=20)

    raw = """select *, a, b, z in (1, 2, 3) from my_table q where h and k > 10"""
    expected = """SELECT
    *,
    a,
    b,
    z in (1, 2, 3)
FROM my_table q
WHERE h AND k > 10
"""
    test_parse_wrapper(raw, expected, debug, line_length=20)

    raw = """select *, a, b, case when true then 5 end as x, case when z in (1, 2, 3) then 0 when z = 10 then 20 else null end as q from my_table q where h and k > 10"""
    expected = """SELECT
    *,
    a,
    b,
    CASE
        WHEN true THEN 5
        END AS x,
    CASE
        WHEN z IN (1, 2, 3) THEN 0
        WHEN z = 10 THEN 20
        ELSE NULL
        END AS q
FROM my_table q
WHERE h AND k > 10
"""
    test_parse_wrapper(raw, expected, debug, line_length=20)


def test():
    test_scan_to_close()
    test_detect_substatement_type()
    test_indent_case_statement()
    test_parse()


@click.command()
@click.argument("file")
@click.option("--line-length", default=100)
def main(file: str, line_length: int):
    f = Path(file)
    raw = f.read_text()
    parsed = parse(raw, line_length=line_length)
    f.write_text(parsed)


if __name__ == "__main__":
    main()
