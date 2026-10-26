"""Query diversification for source discovery.

One literal niche phrase finds one kind of video. A resilient engine searches
several content shapes of the same niche so a narrow phrase cannot end the
run. Query generation is deterministic so a run can be explained and repeated.
"""

FAMILIES = ('podcast', 'interview', 'livestream', 'debate', 'reaction',
            'discussion', 'story', 'full episode')

# Preferred phrasings per known niche. They lead the generated variants so the
# first searches use the wording that already works for this project.
NICHE_TEMPLATES = {
    'gaming': ('gaming livestream', 'full gaming stream', 'gaming podcast',
               'reaction stream', 'tournament stream', 'gaming interview',
               'gaming podcast full episode', 'gaming discussion'),
    'ai & technology': ('AI technology interview demonstration', 'technology podcast',
                        'AI entrepreneur interview', 'technology livestream',
                        'tech debate', 'AI founder podcast', 'technology discussion',
                        'artificial intelligence full episode'),
    'business': ('business podcast full episode', 'entrepreneur interview',
                 'startup founder podcast', 'CEO interview', 'business livestream',
                 'founder story', 'business debate', 'money podcast'),
    'fitness': ('fitness training coach interview', 'fitness podcast',
                'workout coach full episode', 'health interview',
                'fitness livestream', 'athlete story', 'fitness debate',
                'nutrition discussion'),
    'sport': ('football sports full interview', 'sports podcast',
              'athlete interview full episode', 'sports debate',
              'match livestream discussion', 'coach interview',
              'sports story', 'training discussion'),
    'culture & comedy': ('comedy culture podcast interview', 'comedy podcast',
                         'stand up full episode', 'culture debate',
                         'comedy livestream', 'comedian interview',
                         'culture discussion', 'comedy story'),
}


def _slug(value):
    return ' '.join(str(value or '').lower().split())


class QueryGenerator:
    """Generate several search phrasings for one niche."""

    def __init__(self, families=FAMILIES, templates=None, queries_per_niche=8):
        self.families = tuple(families)
        self.templates = dict(templates or NICHE_TEMPLATES)
        if not isinstance(queries_per_niche, int) or isinstance(queries_per_niche, bool) or queries_per_niche < 1:
            raise ValueError('Queries per niche must be a positive integer')
        self.queries_per_niche = queries_per_niche

    @staticmethod
    def niche_name(niche):
        if isinstance(niche, dict):
            return str(niche.get('name') or '')
        return str(niche or '')

    @staticmethod
    def niche_query(niche):
        if isinstance(niche, dict):
            return str(niche.get('query') or '')
        return ''

    def generate(self, niche, limit=None):
        """Return the ordered, deduplicated query variants for one niche."""
        name = _slug(self.niche_name(niche))
        original = self.niche_query(niche).strip()
        queries = []
        for template in self.templates.get(name, ()):
            if template not in queries:
                queries.append(template)
        if original and original not in queries:
            queries.insert(0, original)
        for family in self.families:
            phrase = f'{name} {family}'.strip()
            if phrase and phrase not in queries:
                queries.append(phrase)
        if not queries and original:
            queries = [original]
        count = self.queries_per_niche if limit is None else max(1, int(limit))
        return queries[:count]

    def expand(self, niche, attempted):
        """Progressive expansion: broader and alternative phrasings after a failed family."""
        attempted = {str(item) for item in attempted}
        name = _slug(self.niche_name(niche))
        broader = []
        for family in self.families:
            phrase = f'{name} {family}'.strip()
            if phrase and phrase not in attempted:
                broader.append(phrase)
        for template in self.templates.get(name, ()):
            if template not in attempted:
                broader.append(template)
        original = self.niche_query(niche).strip()
        if original and original not in attempted:
            broader.append(original)
        return [item for item in broader if item not in attempted]
