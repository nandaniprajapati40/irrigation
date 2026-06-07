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
    <sld:Name>kc_style</sld:Name>
    <sld:UserStyle>
      <sld:Title>Kc Raster Style (0.0 to 1.5, step 0.1)</sld:Title>
      <sld:FeatureTypeStyle>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ColorMap type="ramp" extended="true">
              <sld:ColorMapEntry color="#FFD700" quantity="0" label="0"/>
              <sld:ColorMapEntry color="#F3C60B" quantity="0.1" label="0.1"/>
              <sld:ColorMapEntry color="#E6B615" quantity="0.2" label="0.2"/>
              <sld:ColorMapEntry color="#DAA520" quantity="0.3" label="0.3"/>
              <sld:ColorMapEntry color="#B5CA58" quantity="0.4" label="0.4"/>
              <sld:ColorMapEntry color="#90EE90" quantity="0.5" label="0.5"/>
              <sld:ColorMapEntry color="#71E371" quantity="0.6" label="0.6"/>
              <sld:ColorMapEntry color="#51D851" quantity="0.7" label="0.7"/>
              <sld:ColorMapEntry color="#32CD32" quantity="0.8" label="0.8"/>
              <sld:ColorMapEntry color="#2AAC2A" quantity="0.9" label="0.9"/>
              <sld:ColorMapEntry color="#228B22" quantity="1" label="1"/>
              <sld:ColorMapEntry color="#0B710B" quantity="1.1" label="1.1"/>
              <sld:ColorMapEntry color="#2E5A06" quantity="1.2" label="1.2"/>
              <sld:ColorMapEntry color="#8B4513" quantity="1.3" label="1.3"/>
              <sld:ColorMapEntry color="#733909" quantity="1.4" label="1.4"/>
              <sld:ColorMapEntry color="#5C2E00" quantity="1.5" label="1.5"/>
            </sld:ColorMap>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </sld:NamedLayer>
</sld:StyledLayerDescriptor>