import hashlib

import pytest


def prepared(tmp_path):
    from app.repositories.store import Store
    from clipping.orchestrator import Config, Controller
    from campaigns.models import Campaign
    controller = Controller(tmp_path, Config(), emit=lambda _: None)
    store = Store(tmp_path / 'content-reward.db')
    path = tmp_path / 'clip.mp4'
    path.write_bytes(b'local verified export')
    store.save_clip({'id': 'clip', 'order_id': controller.state['id'], 'path': str(path),
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'settings': {'source_clip_plan': {'duration_seconds': 35}, 'transcript': 'Complete useful thought.'}})
    campaign = Campaign(title='Campaign', platform='youtube', rights_confirmed=True,
                        rules_reviewed=True, status='active', rules={'required_hashtags': ['#Example']})
    store.save_campaign(campaign)
    return store, campaign, path


def test_manual_export_is_idempotent_and_never_claims_publication(tmp_path):
    from publishing.manager import PublishingManager
    store, campaign, _ = prepared(tmp_path)
    manager = PublishingManager(store, output=tmp_path / 'prepared')
    metadata = {'caption': 'Useful thought #Example'}
    first = manager.publish('clip', metadata, campaign_id=campaign.id, platform='youtube', key='same')
    second = manager.publish('clip', metadata, campaign_id=campaign.id, platform='youtube', key='same')
    assert first['id'] == second['id']
    assert first['status'] == 'READY' and first['url'] is None and first['external_id'] is None
    assert first['metadata']['adapter_result']['package_path']


def test_validation_changed_content_and_changed_key_input_are_refused(tmp_path):
    from publishing.manager import PublishingManager
    store, campaign, path = prepared(tmp_path)
    manager = PublishingManager(store, output=tmp_path / 'prepared')
    with pytest.raises(ValueError, match='campaign'):
        manager.publish('clip', {'caption': 'Missing hashtag'}, campaign_id=campaign.id, platform='youtube', key='bad')
    manager.publish('clip', {'caption': '#Example'}, campaign_id=campaign.id, platform='youtube', key='first')
    with pytest.raises(ValueError, match='different'):
        manager.publish('clip', {'caption': 'Changed #Example'}, campaign_id=campaign.id, platform='youtube', key='first')
    path.write_bytes(b'changed')
    with pytest.raises(ValueError, match='changed'):
        manager.publish('clip', {'caption': '#Example'}, campaign_id=campaign.id, platform='youtube', key='second')


def test_missing_manual_package_is_rebuilt_and_title_is_preserved(tmp_path):
    import json
    from pathlib import Path
    from publishing.manager import PublishingManager
    store, campaign, _ = prepared(tmp_path)
    manager = PublishingManager(store, output=tmp_path / 'prepared')
    metadata = {'caption': '#Example', 'title': 'Reviewed post title'}
    first = manager.publish('clip', metadata, campaign_id=campaign.id, platform='youtube', key='rebuild')
    path = Path(first['metadata']['adapter_result']['package_path'])
    path.unlink()
    manager.publish('clip', metadata, campaign_id=campaign.id, platform='youtube', key='rebuild')
    assert json.loads(path.read_text())['title'] == metadata['title']
