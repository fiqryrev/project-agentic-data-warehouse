"""refusals: an agent episode is read from its last prompt and classified, without a network."""
from llm import refusals as r


def turn(name, **args):
    import json
    return {"role": "assistant", "tool_calls": [{"function": {"name": name, "arguments": json.dumps(args)}}]}


def tool(text):
    return {"role": "tool", "content": text}


HEAD = [{"role": "system", "content": "s"}, {"role": "user", "content": "QUESTION What was the spend?"}]


def test_tables_never_in_view():
    msgs = HEAD + [turn("retrieve", query="", purpose="information"), tool("TABLE a — b"),
                   turn("run_sql", sql="select 1 from t"), tool("Not run. Fix these first: - Not in view: t.")]
    c = r.classify(msgs)
    assert (c["ending"], c["retrieve_information"], c["retrieve_sql"], c["not_in_view"]) == ("tables_never_in_view", 1, 0, 1)


def test_budget_spent_and_answered():
    spent = HEAD + [turn("run_sql", sql="x"), tool("1 rows\n1"), turn("run_sql", sql="y"),
                    tool("Not run. Fix these first: - Not in view: t."),
                    {"role": "user", "content": "No tool calls left. Call submit now"}]
    assert r.classify(spent)["ending"] == "tool_budget_spent"
    ok = HEAD + [turn("retrieve", query="spend"), tool("TABLE t"), turn("run_sql", sql="x"), tool("1 rows\n1")]
    assert r.classify(ok) | {} and r.classify(ok)["ending"] == "other" and r.classify(ok)["retrieve_sql"] == 1
    assert r.classify(None)["ending"] == "no_episode_found"


def test_episode_is_the_longest_prompt_for_the_question():
    short, long = HEAD + [turn("retrieve", query="a")], HEAD + [turn("retrieve", query="a"), tool("x")]
    other = [{"role": "system", "content": "s"}, {"role": "user", "content": "QUESTION other"}, tool("y"), tool("z")]
    import json
    gens = [{"input": json.dumps(m)} for m in (short, long, other)]
    assert r.episode_messages(gens, "What was the spend?") == long
