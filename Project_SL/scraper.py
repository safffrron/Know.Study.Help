import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
import json

class CourseraScraper:
    def __init__(self):
        self.base_url = "https://www.coursera.org"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
    
    def scrape_courses(self, query, limit=5):
        try:
            # Construct search URL
            search_url = f"{self.base_url}/search?query={quote_plus(query)}"
            
            print(f"Searching Coursera for: '{query}'")
            print(f"URL: {search_url}\n")
            
            # Make request
            response = requests.get(search_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            courses = []
            
            # Find all course cards - they're in <li> tags with specific classes
            course_cards = soup.find_all('li', class_='cds-9')[:limit]
            
            for idx, card in enumerate(course_cards, 1):
                try:
                    course_data = self._extract_course_data(card)
                    if course_data:
                        courses.append(course_data)
                        print(f"{idx}. {course_data['title']}")
                        print(f"   Provider: {course_data['provider']}")
                        print(f"   Type: {course_data['type']}")
                        print(f"   Level: {course_data['level']}")
                        print(f"   Duration: {course_data['duration']}")
                        if course_data.get('rating'):
                            print(f"   Rating: {course_data['rating']} ({course_data['reviews']})")
                        print(f"   Link: {course_data['link']}")
                        print()
                except Exception as e:
                    print(f"Error extracting course {idx}: {e}")
                    continue
            
            return courses
            
        except requests.RequestException as e:
            print(f"Error making request to Coursera: {e}")
            return []
        except Exception as e:
            print(f"Unexpected error: {e}")
            return []
    
    def _extract_course_data(self, card):
        course = {}
        
        # Extract title and link
        title_link = card.find('a', class_='cds-CommonCard-titleLink')
        if title_link:
            title_elem = title_link.find('h3', class_='cds-CommonCard-title')
            if title_elem:
                course['title'] = title_elem.get_text(strip=True)
            
            # Extract link from href attribute
            href = title_link.get('href', '')
            course['link'] = f"{self.base_url}{href}" if href else 'N/A'
            
            # Extract aria-label for additional info (contains type)
            aria_label = title_link.get('aria-label', '')
            if 'COURSE' in aria_label:
                course['type'] = 'Course'
            elif 'SPECIALIZATION' in aria_label:
                course['type'] = 'Specialization'
            elif 'PROFESSIONAL CERTIFICATE' in aria_label:
                course['type'] = 'Professional Certificate'
            else:
                course['type'] = 'N/A'
        
        # Extract provider/partner information
        partner_elem = card.find('p', class_='cds-ProductCard-partnerNames')
        if partner_elem:
            course['provider'] = partner_elem.get_text(strip=True)
        else:
            course['provider'] = 'N/A'
        
        # Ratings are inconsistent in static HTML; omit them to avoid misleading data
        course['rating'] = None
        course['reviews'] = None
        
        # Extract metadata (level, duration)
        metadata_elem = card.find('div', class_='cds-CommonCard-metadata')
        if metadata_elem:
            metadata_text = metadata_elem.get_text(strip=True)
            parts = metadata_text.split('·')
            
            if len(parts) >= 1:
                course['level'] = parts[0].strip()
            else:
                course['level'] = 'N/A'
            
            if len(parts) >= 3:
                course['duration'] = parts[2].strip()
            elif len(parts) >= 2:
                course['duration'] = parts[1].strip()
            else:
                course['duration'] = 'N/A'
        else:
            course['level'] = 'N/A'
            course['duration'] = 'N/A'
        
        # Extract skills
        skills_elem = card.find('p', class_='css-vac8rf')
        if skills_elem and skills_elem.find('strong'):
            skills_text = skills_elem.get_text(strip=True)
            if 'Skills you\'ll gain:' in skills_text:
                skills = skills_text.replace('Skills you\'ll gain:', '').strip()
                course['skills'] = [s.strip() for s in skills.split(',')[:5]]  
            else:
                course['skills'] = []
        else:
            course['skills'] = []
        
        return course
    
    def save_to_json(self, courses, filename='coursera_courses.json'):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(courses, f, indent=2, ensure_ascii=False)
            print(f"\nCourses saved to {filename}")
        except Exception as e:
            print(f"Error saving to JSON: {e}")

if __name__ == "__main__":
    scraper = CourseraScraper()
    
    # Get search query from user
    query = input("Enter your search query: ").strip()
    
    if query:
        # Scrape top 5 courses
        courses = scraper.scrape_courses(query, limit=5)
        
        # Optionally save to JSON
        # if courses:
        #     save = input("\nSave results to JSON? (y/n): ").strip().lower()
        #     if save == 'y':
        #         scraper.save_to_json(courses)
    else:
        print("Please enter a valid search query")