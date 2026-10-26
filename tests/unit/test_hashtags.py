
def test_hashtags_use_niche_and_clip_topic_without_generic_padding():
    from growth.hashtags import HashtagGenerator

    result = HashtagGenerator(niche_keywords={'business', 'podcast'},
        topic_keywords={'pricing', 'startup'}).generate('Pricing strategy for startup founders')

    tags = result['hashtags']
    assert '#business' in tags and '#podcast' in tags
    assert '#pricing' in tags and '#startup' in tags and '#founders' in tags
    assert not {'#fyp', '#viral', '#trending', '#explore', '#success', '#mindset'} & set(tags)
    assert 3 <= result['count'] <= 8


def test_hashtag_generator_does_not_invent_tags_to_reach_minimum():
    from growth.hashtags import HashtagGenerator

    result = HashtagGenerator().generate('And then it was a good day')

    assert result['hashtags'] == []
    assert result['shortfall'] == 3


def test_hashtag_history_ranks_account_proven_tags_and_varies_recent_sets():
    from growth.hashtags import HashtagGenerator

    recent = ['#business #podcast #pricing #startup #founders']
    result = HashtagGenerator(niche_keywords={'business', 'podcast'},
        topic_keywords={'pricing', 'startup', 'founders'},
        account_history={'#pricing': 1.0, '#founders': 0.0},
        recent_posts=recent).generate('Pricing strategy for startup founders')

    assert '#pricing' in result['hashtags']
    assert result['hashtags'] != ['#business', '#podcast', '#pricing', '#startup', '#founders']
    assert result['scores']['#pricing']['account_history'] == 1.0
    assert result['scores']['#business']['freshness'] < 1.0
