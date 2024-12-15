# Import necessary modules for Home Assistant configuration flow
from homeassistant import config_entries
from .const import DOMAIN  # Import the DOMAIN constant

# Define a configuration flow class for the Volcano Integration
class VolcanoIntegrationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """
    Handles the UI configuration flow for the Volcano Integration.
    """
    VERSION = 1  # Version of the configuration flow schema

    async def async_step_user(self, user_input=None):
        """
        Handles the user input during the setup process.

        :param user_input: Input provided by the user
        """
        if user_input is not None:
            # Create a configuration entry upon valid user input
            return self.async_create_entry(title="Volcano Integration", data={})

        # Display a form for user input
        return self.async_show_form(step_id="user")
