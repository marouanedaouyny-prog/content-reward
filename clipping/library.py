"""Niche routing and current delivery availability for the local review library."""

from pathlib import Path
import hashlib
import re


ROOT = Path(__file__).resolve().parents[1] / 'clips'
NICHES = (
    ('sports', 'Sports', ('sport', 'sports')),
    ('streams', 'Streams', ('streams', 'stream', 'streaming')),
    ('business', 'Business', ('business',)),
    ('education', 'Education', ('education',)),
    ('gaming', 'Gaming', ('gaming',)),
    ('ai-technology', 'AI & technology', ('ai & technology',)),
    ('fitness', 'Fitness', ('fitness',)),
    ('comedy', 'Culture & comedy', ('culture & comedy', 'comedy')),
    ('unclassified', 'Needs niche review', ()),
)
IDS = {slug for slug, _, _ in NICHES}
ALIASES = {alias: slug for slug, _, aliases in NICHES for alias in (slug, *aliases)}


TOPIC_PHRASES = (
    ('artificial_intelligence', ('artificial intelligence', 'generative ai', 'large language model',
        'machine learning'), ('ai-technology',)),
    ('film_career', ('acting career', 'film industry', 'movie industry', 'movie set',
        'film set'), ('comedy',)),
    ('sports', ('champions league', 'premier league', 'world cup', 'penalty kick',
        'football match', 'boxing match', 'nba playoffs'), ('sports',)),
    ('business', ('cash flow', 'profit margin', 'customer acquisition', 'sales revenue',
        'company valuation'), ('business',)),
    ('education', ('school curriculum', 'classroom lesson', 'learning objective',
        'teaching students', 'exam preparation'), ('education',)),
    ('streams', ('live stream', 'twitch chat', 'streaming audience', 'chat moderation'), ('streams',)),
    ('gaming', ('video game', 'game development', 'game mechanic', 'esports tournament'), ('gaming',)),
    ('fitness', ('strength training', 'muscle growth', 'workout routine', 'cardio workout'), ('fitness',)),
    ('comedy', ('stand up comedy', 'comedy club', 'comedy set'), ('comedy',)),
)


def _topic_evidence(excerpt):
    # Narrow literal clues only support/veto a discovery label; they never choose
    # another category. Ordinary words such as game, model, team and train do not count.
    text = ' ' + re.sub(r'[^\w]+', ' ', str(excerpt).casefold()).strip() + ' '
    evidence = []
    for topic, phrases, compatible in TOPIC_PHRASES:
        found = [phrase for phrase in phrases if ' ' + phrase + ' ' in text]
        if topic == 'artificial_intelligence' and len(re.findall(r'\bai\b', text)) >= 2:
            found.append('AI (multiple mentions)')
        if found:
            evidence.append(dict(topic=topic, phrases=found, compatible_niches=list(compatible)))
    return evidence


def niche_routing(source, chosen=None, *, excerpt=None, review=None):
    """Explain a conservative route, preserving legacy calls and explicit reviews.

    Phrase evidence is an abstention guard, not semantic classification. New
    unreviewed moments need evidence compatible with their discovery label;
    mixed/unknown topics stay in review. Omitting excerpt preserves old routing.
    """
    labels = source.get('niches') or []
    if isinstance(labels, str):
        labels = [labels]
    matches = {ALIASES[label.casefold()] for label in labels
               if isinstance(label, str) and label.casefold() in ALIASES}
    requested = ALIASES.get(str(chosen).strip().casefold()) if chosen else None
    discovery = next(iter(matches)) if len(matches) == 1 else 'unclassified'
    niche = requested or discovery
    evidence = _topic_evidence(excerpt) if excerpt is not None else []
    result = dict(niche=niche, basis='user_selected' if requested else 'discovery_labels',
        needs_review=niche == 'unclassified', requested_niche=requested,
        discovery_niches=sorted(matches), topic_evidence=evidence, review_reasons=[])
    if review is not None:
        if (not isinstance(review, dict) or not isinstance(review.get('niche'), str)
                or review['niche'] not in IDS - {'unclassified'}
                or not isinstance(review.get('rationale'), str)
                or not review['rationale'].strip() or len(review['rationale']) > 2000):
            raise ValueError('Invalid per-clip niche review: canonical niche and rationale required')
        return dict(result, niche=review['niche'], basis='editorial_review', needs_review=False,
                    review_rationale=review['rationale'].strip())
    if niche == 'unclassified':
        result['review_reasons'] = ['ambiguous_or_missing_discovery_niche']
    elif excerpt is not None:
        reason = ('excerpt_discovery_conflict' if evidence and any(
            niche not in item['compatible_niches'] for item in evidence) else
            'excerpt_topic_unverified' if not evidence else None)
        if reason:
            result.update(needs_review=True, review_reasons=[reason])
            if not requested:
                result.update(niche='unclassified', basis=reason)
        elif not requested:
            result['basis'] = 'excerpt_supported_discovery'
    return result


def route_niche(source, chosen=None, *, excerpt=None, review=None):
    """Return the folder ID; niche_routing also exposes evidence and review flags."""
    return niche_routing(source, chosen, excerpt=excerpt, review=review)['niche']


def niche_folder(root, niche):
    root = Path(root)
    folder = root / (niche if niche in IDS else 'unclassified')
    if not folder.resolve().is_relative_to(root.resolve()):
        raise ValueError('Niche folder must stay inside the delivery root')
    return folder


def delivery_availability(clip, subtitles=None, *, expected_hashes=None, root=None):
    video = Path(clip) if clip else None
    caption = video.with_name(video.stem + '-caption.txt') if video else None
    paths = {'video': video, 'subtitles': Path(subtitles) if subtitles else None,
             'post_caption': caption}
    missing, changed, verified, unchecked = [], [], [], []
    hashes = expected_hashes or {}
    for key, path in paths.items():
        try:
            if path is None or not path.is_file() or path.stat().st_size == 0:
                missing.append(key)
            elif root is not None and (path.is_symlink() or not path.resolve().is_relative_to(Path(root).resolve())):
                changed.append(key)
            elif hashes.get(key):
                with path.open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != hashes[key]:
                        changed.append(key)
                    else:
                        verified.append(key)
            else:
                unchecked.append(key)
        except OSError:
            missing.append(key)
    return {'available': not missing and not changed, 'missing_artifacts': missing,
            'changed_artifacts': changed, 'verified_artifacts': verified, 'unchecked_artifacts': unchecked,
            'integrity': 'recorded_hashes' if len(verified) == len(paths) else 'partial_recorded_hashes'
                         if verified else 'presence_only'}


def clip_availability(clip):
    settings = clip.get('settings') or {}
    hashes = {**(settings.get('delivery_hashes') or {}), 'video': clip['sha256']}
    return delivery_availability(clip.get('path'), clip.get('subtitles'), expected_hashes=hashes)


def niche_library(store, *, root=None):
    root = Path(root) if root is not None else ROOT
    categories = {slug: dict(id=slug, name=name, folder=str(niche_folder(root, slug)),
                            clip_count=0, available_clip_count=0, clips=[])
                  for slug, name, _ in NICHES}
    for clip in store.list_clips():
        if clip.get('status') == 'superseded':
            continue
        settings = clip.get('settings') or {}
        routing = settings.get('niche_routing')
        routing = routing if isinstance(routing, dict) else {}
        niche = settings.get('delivery_niche')
        if niche not in IDS:
            niche = route_niche(settings.get('source') or {}, settings.get('niche'))
        availability = clip_availability(clip)
        original_path = clip['path']
        shown_path, shown_subtitles = original_path, clip.get('subtitles')
        mirror = niche_folder(root, niche) / Path(original_path).name
        if mirror != Path(original_path):
            hashes = {**(settings.get('delivery_hashes') or {}), 'video': clip['sha256']}
            mirrored = delivery_availability(mirror, mirror.with_suffix('.srt'), expected_hashes=hashes, root=root)
            if mirrored['available']:
                availability = mirrored
                shown_path, shown_subtitles = str(mirror), str(mirror.with_suffix('.srt'))
        item = dict(id=clip['id'], order_id=clip['order_id'], path=clip['path'],
                    subtitles=clip.get('subtitles'), caption=clip.get('caption', ''), niche=niche,
                    routing_basis=routing.get('basis') or ('saved_niche' if settings.get('delivery_niche')
                                                          else 'discovery_niche'),
                    niche_routing=routing, needs_niche_review=routing.get('needs_review', niche == 'unclassified'),
                    **availability)
        item.update(path=shown_path, subtitles=shown_subtitles, original_path=original_path)
        category = categories[niche]
        category['clips'].append(item)
        category['clip_count'] += 1
        category['available_clip_count'] += availability['available']
    return dict(root=str(root), categories=list(categories.values()), publishing_enabled=False,
                ranking_note='Saved niche decisions are preserved. New automatic routes use moment evidence; '
                             'ambiguous or unsupported topics need niche review. '
                             'Popular-source signals and editorial ranking do not predict viral results.')
