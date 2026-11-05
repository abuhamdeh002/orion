from voice.conversation import take_command
from voice.speech_output import spoken_chunks


def test_wake_with_a_request():
    assert take_command("hey orion what time is it", False) == "what time is it"
    assert take_command("Orion, open the notes", False) == "open the notes"


def test_hello_ryan_is_a_wake():
    assert take_command("Hello, Ryan.", False) == ""
    assert take_command("Hello Orion", False) == ""
    assert take_command("hey iron", False) == ""
    assert take_command("hey orien what time is it", False) == "what time is it"
    assert take_command("hey ryan what time is it", False) == "what time is it"


def test_bare_wake_and_ignore():
    assert take_command("hey orion", False) == ""
    # A bare greeting with no name does not wake him: TVs and videos say "hello" all the time.
    assert take_command("hey", False) is None
    assert take_command("hello", False) is None
    assert take_command("hello", True) == ""
    assert take_command("what time is it", False) is None


def test_first_sentence_is_its_own_piece():
    chunks = spoken_chunks("It's just after six. The calendar is clear tonight. Then there is a longer bit that can wait.")
    assert chunks[0] == "It's just after six."
    assert len(chunks) <= 3


def test_follow_up_without_the_name():
    assert take_command("and the date", True) == "and the date"
    assert take_command("that's all", True) == "end"


def test_calendar_is_recognized_and_the_clock_stays_instant():
    from types import SimpleNamespace

    from core.quick_reply import instant_reply
    from core.reflex import is_calendar

    assert is_calendar("What's on my calendar today?")
    assert is_calendar("Who are we having a meeting with?")
    reply = instant_reply("what time is it", SimpleNamespace(display_name="Sir"))
    assert reply is not None
    assert reply.startswith("It's ")
    assert instant_reply("what time is it?", SimpleNamespace(display_name="Sir")).startswith("It's ")
    assert instant_reply("do you have the time", SimpleNamespace(display_name="Sir")).startswith("It's ")


def test_orion_stop_cuts_him_off():
    assert take_command("orion stop", False) == "end"
    assert take_command("hey orion stop", False) == "end"
    assert take_command("stop orion", False) == "end"
    assert take_command("Orion, stop", True) == "end"
    assert take_command("stop", True) == "end"
    assert take_command("stop", False) is None
    assert take_command("orion stop the music", False) == "stop the music"


def test_the_name_at_the_end_or_middle_addresses_him_with_the_whole_sentence():
    """'I am the one who made you Orion' was answered with 'Yeah?', as if he had only been called."""
    assert take_command("I am the one who made you Orion", False) == "I am the one who made you"
    assert take_command("I am the one who made you, Orion.", False) == "I am the one who made you"
    assert take_command("what time is it Orion", False) == "what time is it"
    assert take_command("tell me, Orion, what the weather is", False) == "tell me, what the weather is"
    assert take_command("do you know that your name is Orion", False) == "do you know that your name is Orion"
    assert take_command("thanks Orion, that's all", False) == "end" or take_command("thanks Orion, that's all", False) == "thanks that's all"


def test_the_constellation_is_not_him():
    assert take_command("look at the Orion constellation tonight", False) is None
    assert take_command("you can see Orion's belt from here", False) is None
    assert take_command("the Orion nebula is beautiful", False) is None


def test_calling_him_still_works():
    assert take_command("Orion", False) == ""
    assert take_command("hey Orion", False) == ""
    assert take_command("hey Orion what's the time", False) == "what's the time"
