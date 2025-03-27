import os
import logging
from typing import Dict, Any, Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

class PromptManager:
    """
    Manages loading and rendering of prompt templates using Jinja2.
    """
    
    def __init__(self, templates_dir: Optional[str] = None):
        """
        Initialize the prompt manager with a templates directory.
        
        Args:
            templates_dir: Path to the templates directory. If None, defaults to 
                           'prompt_templates' in the same directory as this module.
        """
        if templates_dir is None:
            # Default templates directory is relative to the module directory
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            templates_dir = os.path.join(root_dir, 'prompt_templates')
        
        # Ensure the templates directory exists
        if not os.path.exists(templates_dir):
            logger.warning(f"Templates directory {templates_dir} does not exist. Creating it.")
            os.makedirs(templates_dir, exist_ok=True)
            
        self.templates_dir = templates_dir
        logger.info(f"Initializing PromptManager with templates directory: {templates_dir}")
        
        # Initialize Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )
    
    def render_template(self, template_name: str, **kwargs) -> str:
        """
        Render a template with the given context.
        
        Args:
            template_name: Name of the template file (with .j2 extension)
            **kwargs: Variables to pass to the template
            
        Returns:
            Rendered template as a string
        """
        try:
            template = self.env.get_template(template_name)
            return template.render(**kwargs)
        except Exception as e:
            logger.error(f"Error rendering template {template_name}: {e}")
            # Return a simple fallback to avoid breaking the application
            return f"Error rendering template '{template_name}'. Please check the logs."
    
    def get_template_path(self, template_name: str) -> str:
        """
        Get the full path to a template file.
        
        Args:
            template_name: Name of the template file
            
        Returns:
            Full path to the template file
        """
        return os.path.join(self.templates_dir, template_name)
    
    def create_template_if_not_exists(self, template_name: str, content: str) -> bool:
        """
        Create a template file if it does not exist.
        
        Args:
            template_name: Name of the template file
            content: Content to write to the template file
            
        Returns:
            True if the template was created, False if it already existed
        """
        template_path = self.get_template_path(template_name)
        if os.path.exists(template_path):
            logger.debug(f"Template {template_name} already exists. Skipping creation.")
            return False
        
        try:
            with open(template_path, 'w') as f:
                f.write(content)
            logger.info(f"Created template {template_name}")
            return True
        except Exception as e:
            logger.error(f"Error creating template {template_name}: {e}")
            return False 