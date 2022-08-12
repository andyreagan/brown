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


def process_from(
    x: str, current_line_length: int, max_line_length: int, indent: str
) -> str:
    if re.match(".*?[^\n]+--.*?$", x, re.DOTALL) is not None:
        # test buffer:
        #         buffer = '''stuff
        # -- comment
        # stuff --trailingg comment
        # '''
        search = re.search("(?P<precomment>.*?[^\n]+)--(?P<comment>.*?)$", x, re.DOTALL)
        expression_trailing_comment = search.group("comment").strip()
        # since we found a trailing comment, remove it:
        # buffer = '--'.join(buffer.split('--')[:-1]).strip()
        x = search.group("precomment").strip()
    else:
        expression_trailing_comment = None
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
        return (
            " " + together + format_trailing_comment(expression_trailing_comment) + "\n"
        )
    else:
        return (
            "\n"
            + indent
            + together
            + format_trailing_comment(expression_trailing_comment)
            + "\n"
        )


def process_where(x: str, current_line_len: int, max_line_len: int, indent: str) -> str:
    # we don't really need to split it like this
    # since we just stick it back together
    clauses = [z.strip() for z in x.strip().split("and")]
    oneline = " AND ".join(clauses)
    if len(oneline) + 1 + current_line_len <= max_line_len:
        return " " + oneline + "\n"
    else:
        return "\n" + f"\n{indent}AND ".join(clauses) + "\n"


def scan_to_close(
    remaining_text: str,
    open_char: str = "(",
    close_char: str = ")",
    skip_comments: bool = False,
    debug: bool = False,
) -> str:
    needed_to_close: int = 1
    i: int = 0
    while needed_to_close > 0 and (i + len(close_char) - 1) < len(remaining_text):
        if remaining_text[i : i + len(close_char)] == close_char:
            if debug:
                print(f"Found a close at position {i=}")
            needed_to_close -= 1
            # if we have a longer close char, skip the whole thing
            i += len(close_char) - 1
        if remaining_text[i : i + len(open_char)] == open_char:
            if debug:
                print(f"Found another open at position {i=}")
            needed_to_close += 1
            i += len(open_char) - 1
        i += 1
    if needed_to_close > 0:
        raise RuntimeError("Unbounded group")
    return remaining_text[: i - len(close_char)]


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


def indent_case_statement(
    stmt: str, cur_ind: str, ind: str, max_ll: int, debug: bool = False
) -> str:
    for keyword in {"CASE", "WHEN", "THEN", "ELSE", "END", "AS", "NULL", "IN"}:
        stmt = stmt.replace(" " + keyword.lower() + " ", " " + keyword + " ")

    # first, get out to the end
    match = re.match(r"(?si)CASE(?P<body>.*?)\sEND\s*?(?P<end>.*)", stmt).groupdict()
    if debug:
        print(match)
    # if there is an else, get that
    if len(split := match["body"].split("ELSE ")) > 1:
        body = split[0]
        elsestmt = split[1]
    else:
        body = match["body"].strip()
        elsestmt = None
    stmts = [["WHEN ", x.strip()] for x in body.split("WHEN ") if x.strip() != ""]
    if elsestmt is not None:
        stmts.append(["ELSE ", elsestmt])
    split_stmts = []
    for i in range(len(stmts)):
        # get a leading comment
        leading_comment_lines = 0
        for line in stmts[i][1].split("\n"):
            if re.match("^\s*--", line) is not None:
                leading_comment_lines += 1
        if leading_comment_lines > 0:
            split_stmts += [
                ["", x] for x in stmts[i][1].split("\n")[:leading_comment_lines]
            ] + [
                [
                    stmts[i][0],
                    "\n".join(stmts[i][1].split("\n")[leading_comment_lines:]),
                ]
            ]
        else:
            split_stmts += [stmts[i]]
    if debug:
        print(f"{stmt=} {match=} {body=} {elsestmt=} {stmts=} {split_stmts=}")
    breaking_comments = re.search("\n[ \t]*--", stmt) is not None
    breaking_comments = len(split_stmts) > len(stmts)
    flatten = lambda x: x.replace("\n", " ")
    if (
        len(cur_ind)
        + 5
        + len(flat := " ".join([f"{k}{flatten(v)}" for k, v in split_stmts]))
        + 5
        + len(match["end"])
        <= max_ll
    ) and not breaking_comments:
        return ("CASE " + flat + " END " + match["end"].strip()).strip()
    else:
        # we'll apply indent to trailing lines of statements
        for i in range(len(split_stmts)):
            k, v = split_stmts[i]
            # simply add to the indent
            if debug:
                print(f"{k=}, {v=}")
            if "\n" in v:
                if debug:
                    print("indenting new lines")
                split_stmts[i][1] = v.replace("\n", "\n" + f"{cur_ind}{ind}{ind}")
        return (
            f"CASE\n{cur_ind}{ind}"
            + f"{cur_ind}{ind}".join([f"{k}{v}\n" for k, v in split_stmts])
            + f"{cur_ind}{ind}END "
            + match["end"].strip()
        ).strip()


def process_when(stmt: str, cur_ind: str, ind: str, max_ll: int, debug: bool = False) -> str:
    formatted = ""
    return formatted


def process_else(stmt: str, cur_ind: str, ind: str, max_ll: int, debug: bool = False) -> str:
    formatted = ""
    return formatted


def indent_case_statement_iterative(
    stmt: str, cur_ind: str, ind: str, max_ll: int, debug: bool = False
) -> str:
    """The previous version of indent_case_statement used split() to break
    up the WHEN clauses.
    This approach works for the most simple cases, but gets unworkable with
    wacky comments, nested statements, and other edge cases.
    Here, like in the main loop, we'll go character by character (iteratively)
    to build out the stuff.
    """
    # {"clause": "WHEN ", "condition": "x > 10", "result": "'yes'", "comments": []}
    # {"clause": "ELSE ", "condition": None, "result": "NULL", "comments": []}
    # {"clause": None, "condition": None, "result": None, "comments": ["comment1", "comment2"]}

    group_trailing_comment = None  # will fill with starting comment, if there is one
    group_ending_clause = None  # e.g., "AS q"
    all_clauses = []

    # we can check out of the gate whether or not we can combine the whole thing
    # to a single line
    # breaking_comments = re.search("\n[ \t]*--", stmt) is not None

    # lines = stmt.split("\n")
    # if (res := re.search("(?i)^[ \t]*--(?P<cmt>.*?)", lines[0]) is not None:
    #     group_trailing_comment = res.group('cmt').strip()

    # need a separate comment buffer
    #    when getting into a comment, don't reset the broader buffer
    #    but also don't keep adding to it
    # need to not only keep trailing comments to clause
    # but also, there could be line comments within the clause
    # which means we can't reflow the clause

    i = 4
    assert stmt[:i].upper() == "CASE"
    formatted = "CASE "
    buffer = ""
    current_clause = {}
    while i < len(stmt):
        buffer += stmt[i]
        if debug:
            print(f"{i=} {buffer=} {current_clause=}")
        if stmt[i : i + 2] == "--":
            comment = scan_to_close(
                stmt[i + 2 :], open_char="\n\n", close_char="\n", debug=debug
            )
            if debug:
                print(f"found a comment - scanned to close it: {comment=}")

            if current_clause.get("clause") is None:
                if len(current_clause.get("comments", [])) == 0:
                    current_clause = {
                        "clause": None,
                        "condition": None,
                        "result": None,
                        "comments": [comment.strip()],
                    }
                else:
                    current_clause["comments"].append(comment.strip())
                i += len(comment) + 2
                buffer = buffer[:-1]
            else:
                # don't stick it into the comments:
                # current_clause["comments"].append(comment.strip())
                # add it to the buffer
                i += len(comment) + 2
                buffer += '-'  + comment
            if debug:
                print(f"updated {buffer=} and position {i=}, {stmt[i]=}")
        if stmt[i : i + 4].upper() == "WHEN":
            if current_clause.get('clause') is not None:
                current_clause["result"] = buffer[:-1].strip()
                all_clauses.append(current_clause)
            current_clause = {
                "clause": "WHEN ",
                "condition": None,
                "result": None,
                "comments": [],
            }
            i += 3
            buffer = ""
        if stmt[i : i + 4].upper() == "THEN":
            current_clause["condition"] = buffer[:-1].strip()
            i += 3
            buffer = ""
        if stmt[i : i + 4].upper() == "ELSE":
            current_clause["result"] = buffer[:-1].strip()
            all_clauses.append(current_clause)
            current_clause = {
                "clause": "ELSE ",
                "condition": None,
                "result": None,
                "comments": [],
            }
            i += 3
            buffer = ""
        if stmt[i : i + 3].upper() == "END":
            current_clause["result"] = buffer[:-1].strip()
            all_clauses.append(current_clause)
            group_ending_clause = stmt[i + 3 :]
            break
        i += 1
    return all_clauses


def process_expression(
    buffer: str, remaining: str, indent: str, line_length: int, **kwargs
):
    """This function accepts an expression
    (without trailing ,)
    but otherwise unmodified,
    and checks a few things before attempting to process the expression.
    First, we look ahead in the file to see if there is a comment immediately
    following.
    Second, we break off a trailing comment inside the expression itself.

    In both cases, we return the comment along with the formatted expression
    to the calling function."""
    buffer = buffer.strip()

    # check for a line comment following this expression
    # this can happen when the expression is terminated by a comma
    # the only gap between the end of the expression and the comment
    # has to be spaces: [ \t]*
    # and only search up to the next newline (don't cross newlines)
    if (result := re.search("^[ \t]*--(?P<cmt>.*?)\n", remaining)) is not None:
        lookahead_trailing_comment = result.group("cmt").strip()
    else:
        lookahead_trailing_comment = None
    # can we find a trailing comment in this expression body?
    # this can happen when the select body is terminated by FROM or INTO
    pat = ".*?--(?P<comment>.*?)$"
    if (res := re.search(pat, buffer)) is not None:
        expression_trailing_comment = res.group("comment").strip()
        # since we found a trailing comment, remove it:
        buffer = "--".join(buffer.split("--")[:-1]).strip()
    else:
        expression_trailing_comment = None
    if buffer[:4].upper() == "CASE":
        indented_statement = indent_case_statement(
            buffer, indent, indent, line_length, **kwargs
        )
    else:
        indented_statement = re.sub(r"\s+", " ", buffer)

    if (
        expression_trailing_comment is not None
        and lookahead_trailing_comment is not None
    ):
        raise RuntimeError("Found double comments on expression - shouldnt happen")

    comment = lookahead_trailing_comment
    if expression_trailing_comment is not None:
        comment = expression_trailing_comment

    return {
        "stmt": indented_statement,
        "trailing_comment": expression_trailing_comment,
        "lookahead_comment": lookahead_trailing_comment,
        "comment": comment,
    }


def process_stmt(x: dict, indent: str) -> str:
    """This allows us to use the 'stmt' in the expression list being empty
    to indicate that this wasn't an expression at all, but a comment.
    In which case, we'll just stick the comment in."""

    if (s := x["stmt"]) != "":
        return f"{indent}{s},{format_trailing_comment(x.get('comment'))}"
    else:
        return f"{indent}-- {x['comment'].strip()}"


def process_select(body: str, line_length: int, debug: bool, indent: str, group_trailing_comment) -> str:
    current_ll = len('SELECT')  # 6
    formatted = ""
    group_expressions = []
    group_inline_comments = False
    buffer = ""
    i = 0
    while i < len(body):
        buffer += body[i]
        if body[i] == "(":
            # careful: these could have comments in them and collapsing
            # entirely won't work
            paren_contains = scan_to_close(body[i + 1 :], debug=debug)
            paren_type = detect_substatement_type(paren_contains)
            if paren_type == "list":
                # remove all spaces (not reflowing lists)
                buffer += re.sub(r"\s+", " ", paren_contains.strip()) + ")"
            elif paren_type == "select":
                # remove all spaces still: not reflowing sub selects
                buffer += re.sub(r"\s+", " ", paren_contains.strip()) + ")"
            elif paren_type == "generic":
                # not dealing with these individually yet either
                buffer += re.sub(r"\s+", " ", paren_contains.strip()) + ")"
            # skip ahead
            i += len(paren_contains) + 1
        if body[i] == "{" and body[i + 1] == "{":
            paren_contains = scan_to_close(
                body[i + 2 :], open_char="{{", close_char="}}", debug=debug
            )
            buffer += "{ " + re.sub(r"\s+", " ", paren_contains.strip()) + " }}"
            # skip ahead
            i += len(paren_contains) + 3
        # we're on a new line (just found an expression, or just starting),
        # and now let's check for a breaking comment:
        if buffer == "\n" and body[i + 1 : i + 3] == "--":
            group_inline_comments = True
            i += 3
            rest_of_line = ""
            while body[i] != "\n":
                rest_of_line += body[i]
                i += 1
            if debug:
                print(f"found an inline comment: {rest_of_line=}")
                print(f"advanced cursor to {i=} which is at char {body[i]=}")
            group_expressions.append({"stmt": "", "comment": rest_of_line})
            buffer = ""
            continue
        within_expr_comment_comma_pattern = "\n.*?--.*?,$"
        # assert re.search(within_expr_comment_comma_pattern, '\nstuff--comment,\nstuff-- comment,comment,') is not None
        # assert re.search(within_expr_comment_comma_pattern, '\nstuff--comment,\nstuff,') is None
        # assert re.search(within_expr_comment_comma_pattern, '\nstuff,') is None
        if (
            ((body[i] == ",") or (i == (len(body) - 1)))
            and re.search(within_expr_comment_comma_pattern, buffer) is None
        ):
            if body[i] == ",":
                buffer = buffer[:-1]
                remaining = body[i + 1 :]
            else:
                remaining = ''
            if debug:
                print(f"found an expression: {buffer=}")
            group_expressions.append(
                process_expression(
                    buffer,
                    remaining,
                    indent,
                    line_length,
                    debug=debug,
                )
            )
            if debug:
                print(f"{group_expressions[-1]}")
            if group_expressions[-1].get("lookahead_comment") is not None:
                # we found a trailing comment, so skip to the next line
                match = re.match("[ \t]*--.*?\n", remaining)
                i += len(match.group())
                if debug:
                    print(
                        f"jumped past trailing comment, new current char is {body[i]}"
                    )
            buffer = ""
        i += 1

    expressions_have_newlines = any(
        ["\n" in x.get("stmt", "") for x in group_expressions]
    )
    combined_trailing_comments = format_trailing_comment(
        group_trailing_comment
    ) + "".join(
        [
            format_trailing_comment(x.get("comment"))
            for x in group_expressions
        ]
    )
    flat_stmts = ", ".join([x["stmt"] for x in group_expressions])
    combined_flat_length = (
        current_ll
        + 1
        + len(flat_stmts)
        + len(combined_trailing_comments)
    )
    if (
        not group_inline_comments
        and not expressions_have_newlines
        and (combined_flat_length <= line_length)
    ):
        formatted += (
            " " + flat_stmts + combined_trailing_comments + "\n"
        )
    else:
        # this puts the first expression on the SELECT line
        # formatted += ' ' + f',\n{indent}'.join(group_expressions) + '\n'
        # this starts it on a new line:
        if len(group_expressions) > 1:
            middle = (
                "\n".join(
                    [
                        process_stmt(x, indent)
                        for x in group_expressions[:-1]
                    ]
                )
                + "\n"
            )
        else:
            middle = ""
        formatted += (
            f"{format_trailing_comment(group_trailing_comment)}\n"
            + middle
            + f"{indent}{group_expressions[-1]['stmt']}{format_trailing_comment(group_expressions[-1].get('comment'))}"
            + "\n"
        )

    return formatted


def parse(
    text: str,
    line_length=100,
    debug: bool = True,
    indent=" " * 4,
    starting_indent: str = "",
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
    # -----------------------
    # The line-position of the writing cursor:
    current_ll = starting_indent
    # The high level clause we're in
    # from the list given by `ORDERED_GROUPS`
    # e.g., "SELECT" or "FROM" or "WHERE"
    current_clause = None
    # The output
    formatted = ""
    # The reading buffer for scanning
    buffer = ""
    # Scanning status
    group_expressions = []
    # Three special variables to keep track of things.
    # We'll put these to trailing if we collapse the whole group
    # (otherwise they stay)
    group_trailing_comment = None
    # These limit our ability to collapse the group:
    # we won't collapse if we have comments that break up the group.
    group_inline_comments = False
    # Another special place for a comment is on a new line,
    # after a group's expressions.
    end_group_comment = None
    i = 0
    while i < len(sanitized):
        buffer += sanitized[i]
        if sanitized[i] == "(":
            # careful: these could have comments in them and collapsing
            # entirely won't work
            paren_contains = scan_to_close(sanitized[i + 1 :], debug=debug)
            paren_type = detect_substatement_type(paren_contains)
            if paren_type == "list":
                # remove all spaces (not reflowing lists)
                buffer += re.sub(r"\s+", " ", paren_contains.strip()) + ")"
            elif paren_type == "select":
                # remove all spaces still: not reflowing sub selects
                buffer += re.sub(r"\s+", " ", paren_contains.strip()) + ")"
            elif paren_type == "generic":
                # not dealing with these individually yet either
                buffer += re.sub(r"\s+", " ", paren_contains.strip()) + ")"
            # skip ahead
            i += len(paren_contains) + 1
        if sanitized[i] == "{" and sanitized[i + 1] == "{":
            paren_contains = scan_to_close(
                sanitized[i + 2 :], open_char="{{", close_char="}}", debug=debug
            )
            buffer += "{ " + re.sub(r"\s+", " ", paren_contains.strip()) + " }}"
            # skip ahead
            i += len(paren_contains) + 3
        if debug:
            print(f"{i=}, {sanitized[i]=}, {current_clause=}, {current_ll=}, {buffer=}")
        # detect comments, which we generally leave alone
        if sanitized[i] == "-" and sanitized[i + 1] == "-":
            comment = scan_to_close(
                sanitized[i + 2 :], open_char="\n\n", close_char="\n", debug=debug
            )
            if debug:
                print(f"found a comment - scanned to close it: {comment=}")
            if current_clause is None:
                formatted += '-- ' + comment.strip() + '\n'
                buffer = ""
            else:
                buffer += '- ' + comment.strip() + '\n'
            i += len(comment) + 2
            if debug:
                print(f"updated {buffer=} and position {i=}, {sanitized[i]=}")
        if (x := buffer.upper()) == "SELECT":
            if (match := re.match("[ \t]*--.*?\n", sanitized[i + 1 :])) is not None:
                group_trailing_comment = (
                    re.search("[ \t]*--(?P<comment>.*?)\n", sanitized[i + 1 :])
                    .group("comment")
                    .strip()
                )
                i += len(match.group())
            formatted += x
            current_ll, current_clause, buffer = len(x), x.upper(), ""
        if current_clause == "SELECT":
            select_exits = {"FROM", "INTO"}
            if (exit := buffer.upper()[-4:]) in select_exits:
                # is the exit on it's own line?
                if buffer[-5] == "\n":
                    if debug:
                        print("select exit is on its own line")
                    # was the previous line a comment?
                    previous_line = buffer.split("\n")[-2]
                    if previous_line[:2] == "--":
                        end_group_comment = previous_line[2:]
                        # remove that from the buffer
                        buffer = "\n".join(buffer.split("\n")[:-2]) + " " * 5
                        if debug:
                            print(
                                f"previous line was a pure comment, removing it...new {buffer=}"
                            )

                formatted_select_body = process_select(buffer[:-5], line_length=line_length, debug=debug, indent=indent, group_trailing_comment=group_trailing_comment)

                formatted += formatted_select_body

                if exit == "INTO":
                    raise RuntimeError("No support for INTO clause")
                # now exit
                if end_group_comment is not None:
                    formatted += "-- " + end_group_comment.strip() + "\n"
                group_trailing_comment, end_group_comment, group_inline_comments = (
                    None,
                    None,
                    False,
                )
                current_ll, current_clause, buffer = len(exit), exit.upper(), ""
        if current_clause == "FROM":
            # NATURAL [ INNER | LEFT OUTER | RIGHT OUTER | FULL OUTER ] JOIN right-join-table
            join_starts = {"NATURAL", "INNER", "LEFT", "RIGHT", "FULL", "CROSS", "JOIN"}
            exits = join_starts | set(ORDERED_GROUPS[4:])
            if i == (len(sanitized) - 1):
                formatted += 'FROM' + process_from(buffer, current_ll, line_length, indent)
            else:
                for exit in exits:
                    if (
                        len(buffer) >= len(exit)
                        and buffer[-len(exit) :].upper() == exit
                    ):
                        formatted += 'FROM' + process_from(
                            buffer[: -len(exit)], current_ll, line_length, indent
                        )
                        formatted += exit
                        current_ll, current_clause, buffer = len(exit), exit.upper(), ""
        if current_clause == "WHERE":
            # NATURAL [ INNER | LEFT OUTER | RIGHT OUTER | FULL OUTER ] JOIN right-join-table
            exits = set(ORDERED_GROUPS[5:])
            if i == (len(sanitized) - 1):
                formatted += process_where(buffer, current_ll, line_length, indent)
            else:
                for exit in exits:
                    if (
                        len(buffer) >= len(exit)
                        and buffer[-len(exit) :].upper() == exit
                    ):
                        formatted += process_where(
                            buffer[: -len(exit)], current_ll, line_length
                        )
                        formatted += exit
                        current_ll, current_clause, buffer = len(exit), exit.upper(), ""

        i += 1

    return formatted


def get_trailing_comment(text: str) -> str:
    i = 0
    rest_of_line = ""
    while text[i] != "\n":
        rest_of_line += text[i]
        i += 1
    if "--" in rest_of_line:
        group_trailing_comment = rest_of_line.split("--")[1].strip()
    else:
        group_trailing_comment = None
    return group_trailing_comment


def format_trailing_comment(comment: str) -> str:
    if comment is not None:
        return f"  -- {comment}"
    else:
        return ""


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
