"""
Individual scraper implementations for all job portals
"""
from .indeed_uk import IndeedUKScraper
from .linkedin_jobs import LinkedInJobsScraper
from .cv_library import CVLibraryScraper
from .adzuna import AdzunaScraper
from .totaljobs import TotalJobsScraper
from .reed import ReedScraper
from .talent import TalentScraper
from .glassdoor import GlassdoorScraper
from .ziprecruiter import ZipRecruiterScraper
from .cwjobs import CWJobsScraper
from .jobsora import JobsoraScraper
from .welcometothejungle import WelcomeToTheJungleScraper
from .itjobboard import ITJobBoardScraper
from .trueup import TrueupScraper
from .redefined import RedefinedScraper
from .weworkremotely import WeWorkRemotelyScraper
from .angellist import AngelListScraper
from .jobspresso import JobspressoScraper
from .grabjobs import GrabJobsScraper
from .remoteok import RemoteOKScraper
from .workingnomads import WorkingNomadsScraper
from .workinstartups import WorkInStartupsScraper
from .jobtensor import JobtensorScraper
from .jora import JoraScraper
from .seojobs import SEOJobsScraper
from .careerbuilder import CareerBuilderScraper
from .dice import DiceScraper
from .escapethecity import EscapeTheCityScraper
from .jooble import JoobleScraper
from .otta import OttaScraper
from .remoteco import RemoteCoScraper
from .seljobs import SELJobsScraper
from .flexjobs import FlexJobsScraper
from .dynamitejobs import DynamiteJobsScraper
from .simplyhired import SimplyHiredScraper
from .remotive import RemotiveScraper


# Registry of all available scrapers
SCRAPER_REGISTRY = {
    'Indeed UK': IndeedUKScraper,
    'Linkedin Jobs': LinkedInJobsScraper,
    'CV-Library': CVLibraryScraper,
    'Adzuna': AdzunaScraper,
    'Totaljobs': TotalJobsScraper,
    'Reed': ReedScraper,
    'Talent': TalentScraper,
    'Glassdoor': GlassdoorScraper,
    'ZipRecruiter': ZipRecruiterScraper,
    'CWjobs': CWJobsScraper,
    'Jobsora': JobsoraScraper,
    'WelcometotheJungle': WelcomeToTheJungleScraper,
    'IT Job Board': ITJobBoardScraper,
    'Trueup': TrueupScraper,
    'Redefined': RedefinedScraper,
    'We Work Remotely': WeWorkRemotelyScraper,
    'AngelList (Wellfound)': AngelListScraper,
    'Jobspresso': JobspressoScraper,
    'Grabjobs': GrabJobsScraper,
    'Remote OK': RemoteOKScraper,
    'Working Nomads': WorkingNomadsScraper,
    'WorkInStartups': WorkInStartupsScraper,
    'Jobtensor': JobtensorScraper,
    'Jora': JoraScraper,
    'SEOJobs.com': SEOJobsScraper,
    'CareerBuilder': CareerBuilderScraper,
    'Dice': DiceScraper,
    'Escape The City': EscapeTheCityScraper,
    'Jooble': JoobleScraper,
    'Otta': OttaScraper,
    'Remote.co': RemoteCoScraper,
    'SEL Jobs': SELJobsScraper,
    'FlexJobs': FlexJobsScraper,
    'Dynamite Jobs': DynamiteJobsScraper,
    'SimplyHired': SimplyHiredScraper,
    'Remotive': RemotiveScraper,
}


def get_scraper(portal_name: str, **kwargs):
    """
    Get scraper instance by portal name
    
    Args:
        portal_name: Name of the job portal
        **kwargs: Arguments to pass to scraper constructor
        
    Returns:
        Scraper instance or None
    """
    scraper_class = SCRAPER_REGISTRY.get(portal_name)
    if scraper_class:
        return scraper_class(**kwargs)
    return None

