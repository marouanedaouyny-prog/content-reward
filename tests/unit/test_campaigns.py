import pytest


def test_structured_rules_preserve_platforms_hashtags_and_duration():
    from campaigns.rules import parse_rules
    parsed = parse_rules({'min_duration': 20, 'max_duration': 60,
                          'allowed_platforms': ['youtube_shorts'], 'required_hashtags': ['#Example']})
    assert not parsed.requires_review
    assert parsed.rules.allowed_platforms == ['youtube']
    assert parsed.rules.min_duration == 20


def test_prose_rule_extraction_never_claims_complete_understanding():
    from campaigns.rules import parse_rules
    parsed = parse_rules('Clips between 20 and 40 seconds. Must include #Example. Ask the creator before posting.')
    assert parsed.rules.min_duration == 20 and parsed.rules.max_duration == 40
    assert '#Example' in parsed.rules.required_hashtags
    assert parsed.requires_review and parsed.warnings


def test_campaign_validation_checks_content_destination_and_review():
    from campaigns.models import Campaign
    from campaigns.validation import validate_campaign
    campaign = Campaign(title='Reviewed campaign', platform='youtube', rules_reviewed=True,
        rights_confirmed=True, status='active', rules={'min_duration': 20, 'max_duration': 60,
            'allowed_platforms': ['youtube'], 'required_hashtags': ['#Example'], 'forbidden_topics': ['gambling']})
    good = {'duration_seconds': 35, 'transcript': 'A useful complete explanation.', 'source_id': 'source'}
    assert validate_campaign(campaign, good, {'caption': 'Useful #example'}, 'youtube', for_publication=True).eligible
    failed = validate_campaign(campaign, {**good, 'duration_seconds': 80, 'transcript': 'gambling advice'},
                               {'caption': 'Missing hashtag'}, 'tiktok', for_publication=True)
    assert not failed.eligible and len(failed.violations) >= 4
    campaign.rights_confirmed = False
    assert not validate_campaign(campaign, good, {'caption': '#Example'}, 'youtube', for_publication=True).eligible


def test_inverted_or_nonfinite_rules_are_rejected():
    from campaigns.models import Rules
    with pytest.raises(ValueError):
        Rules(min_duration=60, max_duration=20)
    with pytest.raises(ValueError):
        Rules(min_duration=float('nan'))


def test_campaign_is_persisted_and_rejects_invalid_source_before_download(tmp_path, monkeypatch):
    from campaigns.models import Campaign
    from clipping.orchestrator import Config, Controller, SetupIssue
    from clipping.batch import create_clip_job
    from clipping import sections
    controller = Controller(tmp_path, Config(partial_downloads=True, clip_count=20), emit=lambda _: None)
    campaign = Campaign(title='Source restricted', platform='youtube', rules={'allowed_source_ids': ['allowed']})
    controller.store.save_campaign(campaign)
    controller.config.campaign_id = campaign.id
    source = {'id': 'blocked', 'title': 'Test source', 'url': 'https://www.youtube.com/watch?v=abcdefghijk'}
    controller.state['source_selection'] = source
    moment = {'clip_plan': {'start_seconds': 0, 'duration_seconds': 35}, 'caption': 'Complete thought.',
              'quality': {'completed_ending': True, 'speech_ratio': 1.0, 'largest_speech_gap': 0}}
    monkeypatch.setattr(sections, 'download_section', lambda *args: pytest.fail('Downloaded invalid campaign source'))
    with pytest.raises(SetupIssue) as error:
        create_clip_job(controller, {'number': 1}, moment, {}, 1, 0)
    assert error.value.code == 'campaign_validation_failed'
    assert controller.store.get_campaign(campaign.id).title == campaign.title
