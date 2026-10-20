# Main Entry Point
# Automation Empire OS - Content Rewards Automation

import argparse
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from project.db.models import init_db, seed_default_settings
from project.config.settings import get_settings


def setup_logging(level: str = "INFO"):
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def init_database():
    """Initialize the database."""
    settings = get_settings()
    os.makedirs(os.path.dirname(settings.database_url.replace("sqlite:///", "")), exist_ok=True)
    os.makedirs(settings.storage_dir, exist_ok=True)
    
    session = init_db(settings.database_url)
    seed_default_settings(session)
    session.close()
    print("Database initialized successfully")


def run_campaign_discovery():
    """Discover new campaigns."""
    from project.skills.campaign_research.skill import discover_campaigns
    result = discover_campaigns()
    print(f"Discovered {len(result)} new campaigns")


def run_campaign_analysis(campaign_id: str = None):
    """Analyze campaign requirements."""
    from project.skills.campaign_parser.skill import parse_campaign
    from project.skills.campaign_research.skill import CampaignResearchSkill
    from project.db.models import init_db, Campaign
    
    if campaign_id:
        result = parse_campaign(campaign_id)
        print(f"Analyzed campaign {campaign_id}: {result}")
    else:
        # Analyze all DISCOVERED campaigns
        session = init_db()
        campaigns = session.query(Campaign).filter(Campaign.status == "DISCOVERED").all()
        session.close()
        
        for camp in campaigns:
            result = parse_campaign(camp.id)
            print(f"Analyzed {camp.external_campaign_id}: eligible={result['eligible']}")


def run_video_processing(source_media_id: str = None):
    """Process source media into clips."""
    from project.skills.video_processing.skill import process_source_media
    from project.skills.content_strategy.skill import generate_clip_plans
    from project.skills.compliance.skill import run_compliance_check
    from project.db.models import init_db, SourceMedia, Clip, Campaign, ClipPlan
    
    session = init_db()
    
    if source_media_id:
        media_ids = [source_media_id]
    else:
        # Process all DOWNLOADED sources
        media_ids = [m.id for m in session.query(SourceMedia).filter(SourceMedia.status == "DOWNLOADED").all()]
    
    session.close()
    
    for media_id in media_ids:
        print(f"Processing source {media_id}...")
        result = process_source_media(media_id)
        print(f"  Result: {result}")


def run_compliance_checks(clip_id: str = None, platform: str = None):
    """Run compliance checks on clips."""
    from project.skills.compliance.skill import run_compliance_check
    from project.db.models import init_db, Clip
    
    session = init_db()
    
    if clip_id and platform:
        clips = [(clip_id, platform)]
    else:
        # Check all GENERATED clips
        clips = [(c.id, c.aspect_ratio) for c in session.query(Clip).filter(Clip.status == "GENERATED").all()]
    
    session.close()
    
    for cid, plat in clips:
        print(f"Checking clip {cid} on {plat}...")
        result = run_compliance_check(cid, "", plat)  # campaign_id needed
        print(f"  Result: {result.status} (score: {result.score:.1f})")


def run_publishing(clip_id: str = None, platform: str = None, account_id: str = None):
    """Publish clips to social platforms."""
    import asyncio
    from project.skills.social_publishing.skill import publish_clip
    from project.db.models import init_db, Clip, SocialAccount, SocialPost, SocialPostStatus
    
    session = init_db()
    
    if clip_id and platform and account_id:
        clips = [(clip_id, platform, account_id)]
    else:
        # Publish all QA_PASSED clips
        clips = []
        for clip in session.query(Clip).filter(Clip.status == "QA_PASSED").all():
            accounts = session.query(SocialAccount).filter(
                SocialAccount.status == "ACTIVE"
            ).all()
            for account in accounts:
                # Check if already published
                existing = session.query(SocialPost).filter(
                    SocialPost.clip_id == clip.id,
                    SocialPost.social_account_id == account.id,
                    SocialPost.status == SocialPostStatus.PUBLISHED
                ).first()
                if not existing:
                    clips.append((clip.id, account.platform.value, account.id))
    
    session.close()
    
    for cid, plat, acc_id in clips:
        print(f"Publishing clip {cid} to {plat}...")
        result = asyncio.run(publish_clip(cid, plat, acc_id))
        print(f"  Result: {result}")


def run_submissions():
    """Submit published clips to Content Rewards."""
    from project.skills.submission.skill import submit_clip
    from project.db.models import init_db, Clip, SocialPost, SocialPostStatus, Submission, SubmissionStatus
    
    session = init_db()
    
    # Find clips that are PUBLISHED but not submitted
    submissions_made = 0
    for post in session.query(SocialPost).filter(
        SocialPost.status == SocialPostStatus.PUBLISHED
    ).all():
        clip = session.query(Clip).filter(Clip.id == post.clip_id).first()
        if not clip:
            continue
        
        # Check if already submitted
        existing = session.query(Submission).filter(
            Submission.clip_id == clip.id,
            Submission.platform == post.platform.value
        ).first()
        
        if not existing:
            result = submit_clip(
                campaign_id=clip.campaign_id,
                clip_id=clip.id,
                platform=post.platform.value,
                creator_id="creator_001"  # Would come from account
            )
            print(f"Submitted clip {clip.id} to {post.platform.value}: {result}")
            submissions_made += 1
    
    session.close()
    print(f"Made {submissions_made} submissions")


def run_analytics_sync(submission_id: str = None):
    """Sync analytics from social platforms."""
    import asyncio
    from project.skills.analytics.skill import sync_analytics
    
    if submission_id:
        result = asyncio.run(sync_analytics(submission_id))
        print(f"Synced analytics for {submission_id}: {len(result)} snapshots")
    else:
        result = asyncio.run(sync_analytics())
        print(f"Analytics sync: {result}")


def run_payout_check():
    """Check payouts and validation windows."""
    from project.skills.payout_tracking.skill import check_payouts
    result = check_payouts()
    print(f"Payout check: {result}")


def run_recovery():
    """Recover failed jobs."""
    from project.skills.recovery.skill import recover_jobs
    result = recover_jobs()
    print(f"Recovery: {result}")


def run_full_pipeline():
    """Run the complete automation pipeline."""
    print("=== Starting Full Pipeline ===")
    
    print("\n1. Campaign Discovery...")
    run_campaign_discovery()
    
    print("\n2. Campaign Analysis...")
    run_campaign_analysis()
    
    print("\n3. Video Processing...")
    run_video_processing()
    
    print("\n4. Compliance Checks...")
    run_compliance_checks()
    
    print("\n5. Publishing...")
    run_publishing()
    
    print("\n6. Submissions...")
    run_submissions()
    
    print("\n7. Analytics Sync...")
    run_analytics_sync()
    
    print("\n8. Payout Check...")
    run_payout_check()
    
    print("\n9. Recovery...")
    run_recovery()
    
    print("\n=== Pipeline Complete ===")


def main():
    parser = argparse.ArgumentParser(description="Automation Empire OS - Content Rewards Automation")
    parser.add_argument("--init-db", action="store_true", help="Initialize database")
    parser.add_argument("--discover", action="store_true", help="Discover campaigns")
    parser.add_argument("--analyze", nargs="?", const="all", help="Analyze campaigns")
    parser.add_argument("--process", nargs="?", const="all", help="Process source media")
    parser.add_argument("--compliance", nargs="?", const="all", help="Run compliance checks")
    parser.add_argument("--publish", nargs="?", const="all", help="Publish clips")
    parser.add_argument("--submit", action="store_true", help="Submit to Content Rewards")
    parser.add_argument("--analytics", nargs="?", const="all", help="Sync analytics")
    parser.add_argument("--payouts", action="store_true", help="Check payouts")
    parser.add_argument("--recover", action="store_true", help="Recover failed jobs")
    parser.add_argument("--full", action="store_true", help="Run full pipeline")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    
    args = parser.parse_args()
    setup_logging(args.log_level)
    
    if args.init_db:
        init_database()
    
    if args.full:
        run_full_pipeline()
    else:
        if args.discover:
            run_campaign_discovery()
        if args.analyze:
            run_campaign_analysis(None if args.analyze == "all" else args.analyze)
        if args.process:
            run_video_processing(None if args.process == "all" else args.process)
        if args.compliance:
            run_compliance_checks()
        if args.publish:
            run_publishing()
        if args.submit:
            run_submissions()
        if args.analytics:
            run_analytics_sync()
        if args.payouts:
            run_payout_check()
        if args.recover:
            run_recovery()
    
    if not any(vars(args).values()):
        parser.print_help()


if __name__ == "__main__":
    main()