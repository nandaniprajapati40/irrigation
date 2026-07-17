<?xml version="1.0" encoding="UTF-8"?>
<sld:StyledLayerDescriptor version="1.0.0"
 xmlns="http://www.opengis.net/sld"
 xmlns:sld="http://www.opengis.net/sld"
 xmlns:ogc="http://www.opengis.net/ogc"
 xmlns:xlink="http://www.w3.org/1999/xlink"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xsi:schemaLocation="http://www.opengis.net/sld
   http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd">

  <sld:NamedLayer>
    <sld:Name>savi_style</sld:Name>
    <sld:UserStyle>
      <sld:Title>SAVI Raster Style (-1.0 to 1.0, step 0.1)</sld:Title>
      <sld:FeatureTypeStyle>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ColorMap type="ramp" extended="true">
              <sld:ColorMapEntry color="#8B0000" quantity="-1" label="-1"/>
              <sld:ColorMapEntry color="#9E0B00" quantity="-0.9" label="-0.9"/>
              <sld:ColorMapEntry color="#B21700" quantity="-0.8" label="-0.8"/>
              <sld:ColorMapEntry color="#C52200" quantity="-0.7" label="-0.7"/>
              <sld:ColorMapEntry color="#D82E00" quantity="-0.6" label="-0.6"/>
              <sld:ColorMapEntry color="#EC3900" quantity="-0.5" label="-0.5"/>
              <sld:ColorMapEntry color="#FF4500" quantity="-0.4" label="-0.4"/>
              <sld:ColorMapEntry color="#FF5D00" quantity="-0.3" label="-0.3"/>
              <sld:ColorMapEntry color="#FF7500" quantity="-0.2" label="-0.2"/>
              <sld:ColorMapEntry color="#FF8D00" quantity="-0.1" label="-0.1"/>
              <sld:ColorMapEntry color="#FFA500" quantity="0" label="0"/>
              <sld:ColorMapEntry color="#FFD200" quantity="0.1" label="0.1"/>
              <sld:ColorMapEntry color="#FFFF00" quantity="0.2" label="0.2"/>
              <sld:ColorMapEntry color="#D6FF17" quantity="0.3" label="0.3"/>
              <sld:ColorMapEntry color="#ADFF2F" quantity="0.4" label="0.4"/>
              <sld:ColorMapEntry color="#68C529" quantity="0.5" label="0.5"/>
              <sld:ColorMapEntry color="#228B22" quantity="0.6" label="0.6"/>
              <sld:ColorMapEntry color="#117811" quantity="0.7" label="0.7"/>
              <sld:ColorMapEntry color="#006400" quantity="0.8" label="0.8"/>
              <sld:ColorMapEntry color="#004C00" quantity="0.9" label="0.9"/>
              <sld:ColorMapEntry color="#003300" quantity="1" label="1"/>
            </sld:ColorMap>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </sld:NamedLayer>
</sld:StyledLayerDescriptor>