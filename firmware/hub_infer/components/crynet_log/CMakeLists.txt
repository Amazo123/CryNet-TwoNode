idf_component_register(
    SRCS "crynet_log.c"
    INCLUDE_DIRS "include"
    REQUIRES spiffs crynet_clock log esp_timer
)
