import re
import unittest

from .brown import (
    detect_substatement_type,
    indent_case_statement,
    indent_case_statement_iterative,
    parse,
    scan_to_close,
)


def test_scan_to_close(**kwargs) -> None:
    assert scan_to_close("a)", **kwargs) == "a"
    assert scan_to_close("(a))", **kwargs) == "(a)"
    assert scan_to_close("a}}", close_char="}}", **kwargs) == "a"
    assert scan_to_close("(a))", **kwargs) == "(a)"
    assert scan_to_close("{{a}} }}", close_char="}}", **kwargs) == "{{a"
    assert scan_to_close("{{a}} }}", close_char="}}", open_char="{{", **kwargs) == "{{a}} "
    assert scan_to_close("{{a}}}}", close_char="}}", open_char="{{", **kwargs) == "{{a}}"

    unittest.TestCase().assertRaises(RuntimeError, scan_to_close, "(a)")
    assert scan_to_close("(z(x(a)1)2)3)", **kwargs) == "(z(x(a)1)2)3"


# def test_get_trailing_comment() -> None:
#     sanitized = """T-- comment
# """
#     assert get_trailing_comment(sanitized) == "comment"
#     sanitized = """T--comment
# """
#     assert get_trailing_comment(sanitized) == "comment"
#     sanitized = """T    --comment
# """
#     re.match("[ \t]*--(.*?)\n", sanitized[1:])
#     assert get_trailing_comment(sanitized) == "comment"
#     sanitized = """T
# --"""
#     re.match("\s*--", sanitized[1:])
#     assert get_trailing_comment(sanitized) is None


def test_detect_substatement_type() -> None:
    detect_substatement_type("select x from z") == "select"
    detect_substatement_type("x, y, z") == "list"
    detect_substatement_type("'x', 'y', 'z'") == "list"
    detect_substatement_type("1, 2, 3") == "list"
    detect_substatement_type("case when ... then else end as z") == "generic"
    detect_substatement_type("case when x in (z, y, j) then else end as z") == "generic"
    detect_substatement_type("z == 10 and y = 5") == "generic"


def test_indent_case_statement(**kwargs) -> None:
    print(
        indent_case_statement(
            "case when x = 10 then 5 when z = 3 then 2 else 20 end as test",
            " " * 4,
            " " * 4,
            1000,
        )
    )
    assert (
        indent_case_statement(
            "case when x = 10 then 5 when z = 3 then 2 else 20 end as test",
            " " * 4,
            " " * 4,
            1000,
            **kwargs,
        )
        == "CASE WHEN x = 10 THEN 5 WHEN z = 3 THEN 2 ELSE 20 END AS test"
    )
    assert (
        indent_case_statement(
            "case when x = 10 then 5 when z = 3 then 2 else 20 end as test",
            "",
            " " * 4,
            20,
            **kwargs,
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
            **kwargs,
        )
        == """CASE
        WHEN z IN (1, 2, 3) THEN 0
        WHEN z = 10 THEN 20
        ELSE NULL
        END AS q"""
    )

    buffer = "\nCASE\nWHEN PROD_GROUP = 'retail' THEN\n-- for CM val files [2=MPR, 17=Datalife (CM2000 AND SWL)] use last 2 digits to make suffix\n-- otherwise there should be no suffix\n-- what about CM migrations to coverpath (sanderling)?\n-- second piece here gets those: source=22 is haven\n-- a _single_ policy needs this to not have a duplicate\nCASE\nWHEN\n((VAL_FILE_IND IN (2, 17)) OR ((VAL_FILE_IND = 22) AND (mm_cm = 'CM'))) AND (RIGHT(PK_POL_NO::VARCHAR, 2)::INT BETWEEN 1 AND 13)\nTHEN CHR(64 + RIGHT(PK_POL_NO::VARCHAR, 2)::int) -- A thru M\nELSE PK_AGMT_SFX\nEND\n-- WHEN prod_typ_groups.PROD_GROUP IN ('eb', 'worksite') THEN\n-- CASE WHEN pk_agmt_sfx = '0' THEN 'N'\n-- ELSE pk_agmt_sfx END\n-- use the one that's nulled:\nELSE PK_AGMT_SFX\nEND AS PK_AGMT_SFX_FIX,"

    indent_case_statement(buffer[:-1].strip(), " " * 4, " " * 4, 20, **kwargs)


def test_indent_case_statement_iterative(**kwargs) -> None:
    raw = "case when x = 10 then 5 when z = 3 then 2 else 20 end as test"
    expected = "CASE WHEN x = 10 THEN 5 WHEN z = 3 THEN 2 ELSE 20 END AS test"
    parsed = indent_case_statement_iterative(
        raw,
        " " * 4,
        " " * 4,
        1000,
        **kwargs,
    )
    print(raw)
    print(expected)
    print(parsed)
    # assert expected == parsed

    expected = """CASE
    WHEN x = 10 THEN 5
    WHEN z = 3 THEN 2
    ELSE 20
    END AS test"""
    parsed = indent_case_statement_iterative(
        raw,
        "",
        " " * 4,
        20,
        **kwargs,
    )
    print(raw)
    print(expected)
    print(parsed)
    # assert expected == parsed

    raw = " case when z in (1, 2, 3) then 0 when z = 10 then 20 else null end as q ".strip()
    expected = """CASE
    WHEN z IN (1, 2, 3) THEN 0
    WHEN z = 10 THEN 20
    ELSE NULL
    END AS q"""
    parsed = indent_case_statement_iterative(
        raw,
        " " * 4,
        " " * 4,
        20,
        **kwargs,
    )
    print(raw)
    print(expected)
    print(parsed)
    # assert expected == parsed

    raw = """CASE
-- leading case statement comment
WHEN z IN (1, 2, 3) THEN 0
-- sandwiched
-- sandwiched 2
-- sandwiched 3
WHEN z = 10 THEN 20  -- trailing
WHEN z = 10 -- trailing
-- split the when
-- statement into two halves!
THEN 20
-- sandwiched between when and else
-- sandwiched between when and else 2
ELSE NULL
-- post else
END
AS q"""
    expected = """CASE
    -- leading case statement comment
    WHEN z IN (1, 2, 3) THEN 0
    -- sandwiched
    -- sandwiched 2
    -- sandwiched 3
    WHEN z = 10 THEN 20  -- trailing
    WHEN z = 10 -- trailing
        -- split the when
        -- statement into two halves!
        THEN 20
    -- sandwiched between when and else
    -- sandwiched between when and else 2
    ELSE NULL
    -- post else
    END AS q"""
    parsed = indent_case_statement_iterative(
        raw,
        " " * 4,
        " " * 4,
        20,
    )
    print(raw)
    print(expected)
    print(parsed)
    assert expected == parsed


def test_process_expression() -> None:
    # Test the inner-expression search for a trailing comment:
    buffer = """stuff
-- comment
stuff --trailingg comment
"""
    pat = ".*?--(?P<comment>.*?)$"
    assert re.search(pat, buffer) is not None
    assert re.search(pat, buffer).group("comment").strip() == "trailingg comment"
    # check that we remove the comment:
    new_buffer = "--".join(buffer.split("--")[:-1]).strip()
    assert new_buffer == "stuff\n-- comment\nstuff"


def test_parse_wrapper(raw: str, expected: str, debug: bool = True, **kwargs) -> None:
    if debug:
        print("=" * 80)
        print("=" * 80)
    parsed = parse(raw, debug=debug, **kwargs)
    # Mark the end of the debug output from parse()
    if debug:
        print("=" * 80)
        print(raw)
        print("=" * 80)
        print(expected)
        print("=" * 80)
        print(parsed)
    # Show the first character where they are different,
    # since it's about to fail:
    if debug and parsed != expected:
        print(f"{len(expected)=} {len(parsed)=}")
        for i in range(len(expected)):
            if expected[i] != parsed[i]:
                print(f"{i=}, {expected[i]=}, {parsed[i]=}")
                break
    assert parsed == expected


def test_parse(**kwargs) -> None:
    raw = """select *, a, b,z from my_table q where h and k > 10"""
    expected = """SELECT *, a, b, z
FROM my_table q
WHERE h AND k > 10
"""
    test_parse_wrapper(raw, expected, **kwargs)

    # Collapse these comments within the line length limit
    raw = """-- hello comment
SELECT  -- collapsed comment 1,
    *,  -- 2
    a,  -- 3
    b,
    z  -- 4
  -- hello again comment
FROM my_table q -- comments are good!
WHERE h AND k > 10
"""
    expected = """-- hello comment
SELECT *, a, b, z  -- collapsed comment 1,  -- 2  -- 3  -- 4
-- hello again comment
FROM my_table q  -- comments are good!
WHERE h AND k > 10
"""
    test_parse_wrapper(raw, expected, **kwargs)

    # Cannot collapse these comments within the line length limit
    # Still can enforce some other things
    raw = """SELECT-- collapsed comment 1
    *,-- collapsed comment 2
    a,      -- collapsed comment 3
    b,
    z  -- collapsed comment 4
  --hello again comment
FROM my_table q -- comments are good!
WHERE h AND k > 10
"""
    expected = """SELECT  -- collapsed comment 1
    *,  -- collapsed comment 2
    a,  -- collapsed comment 3
    b,
    z  -- collapsed comment 4
-- hello again comment
FROM my_table q  -- comments are good!
WHERE h AND k > 10
"""
    test_parse_wrapper(raw, expected, **kwargs)

    raw = """SELECT
    *,
    a,
    -- don't, collapse, this, block, keep, comment
    b,
    z
FROM my_table q
WHERE h AND k > 10
"""
    test_parse_wrapper(raw, raw, **kwargs)

    raw = """SELECT
    *,
    a,
    -- don't, collapse, this, block, keep, comment
    -- keep a second comment
    -- and a third
    b,
    -- la dee da
    z
FROM my_table q
WHERE h AND k > 10
"""
    test_parse_wrapper(raw, raw, **kwargs)

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
    test_parse_wrapper(raw, expected, line_length=20, **kwargs)

    raw = """select *, a, b, z in (1, 2, 3) from my_table q where h and k > 10"""
    expected = """SELECT
    *,
    a,
    b,
    z in (1, 2, 3)
FROM my_table q
WHERE h AND k > 10
"""
    test_parse_wrapper(raw, expected, line_length=20, **kwargs)

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
    test_parse_wrapper(raw, expected, line_length=20, **kwargs)


#     raw = """SELECT *,
#     CASE
#         -- leading case statement comment
#         WHEN z IN (1, 2, 3) THEN 0
#         -- sandwiched
#         -- sandwiched 2
#         -- sandwiched 3
#         WHEN z = 10 THEN 20  -- trailing
#         -- sandwiched between when and else
#         -- sandwiched between when and else 2
#         ELSE NULL
#         -- post else
#         END AS q
# FROM my_table q
# WHERE h AND k > 10
# """
#     test_parse_wrapper(raw, raw, **kwargs)


if __name__ == "__main__":
    debug: bool = True
    test_scan_to_close(debug=debug)
    test_detect_substatement_type()
    test_indent_case_statement(debug=debug)
    test_indent_case_statement_iterative(debug=debug)
    # test_get_trailing_comment()
    test_process_expression()
    test_parse(debug=debug)
